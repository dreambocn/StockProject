from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import re
from html import unescape
from urllib.parse import urljoin

import httpx

from app.integrations.policy_provider import PolicyDocumentSeed


Loader = Callable[[], Awaitable[list[dict[str, object]]]]
MIIT_LIST_API_URL = (
    "https://www.miit.gov.cn/api-gateway/jpaas-publish-server/front/page/build/unit"
    "?parseType=buildstatic"
    "&webId=8d828e408d90447786ddbe128d495e9e"
    "&tplSetId=209741b2109044b5b7695700b2bec37e"
    "&pageType=column"
    "&tagId=%E5%BD%93%E5%89%8D%E6%A0%8F%E7%9B%AE_list"
    "&editType=null"
    "&pageId=7df23bf39e2d42b793ebfcc3319015b7"
)
MIIT_BASE_URL = "https://www.miit.gov.cn"
MIIT_TIMEOUT_SECONDS = 30.0
MIIT_DETAIL_FETCH_LIMIT = 12
MIIT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = unescape(str(value))
    normalized = re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()
    return normalized or None


def _parse_miit_datetime_to_iso(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None

    matched = re.search(
        r"(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?",
        text,
    )
    if not matched:
        return None
    year, month, day, hour, minute, second = matched.groups()
    return (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        f"T{int(hour or '0'):02d}:{int(minute or '0'):02d}:{int(second or '0'):02d}+08:00"
    )


def _parse_meta_content(payload: str, meta_name: str) -> str | None:
    matched = re.search(
        rf'<meta[^>]+name=["\']{re.escape(meta_name)}["\'][^>]+content=["\'](?P<value>[^"\']*)["\']',
        payload,
        flags=re.IGNORECASE,
    )
    if not matched:
        return None
    return _clean_text(matched.group("value"))


def _extract_attachment_urls(payload: str) -> list[str]:
    attachment_urls: list[str] = []
    for matched in re.finditer(
        r'href="(?P<value>(?:https://www\.miit\.gov\.cn|/)[^"]+\.(?:pdf|doc|docx|xls|xlsx|zip))"',
        payload,
        flags=re.IGNORECASE,
    ):
        attachment_url = urljoin(MIIT_BASE_URL, matched.group("value"))
        if attachment_url not in attachment_urls:
            attachment_urls.append(attachment_url)
    return attachment_urls


def _parse_miit_unit_payload(payload: str) -> list[dict[str, object]]:
    data = json.loads(payload)
    if not isinstance(data, dict):
        return []
    html = data.get("data", {}).get("html") if isinstance(data.get("data"), dict) else None
    if not isinstance(html, str):
        return []

    rows: list[dict[str, object]] = []
    for matched in re.finditer(
        r'<a[^>]+href="(?P<url>/jgsj/kjs/wjfb/art/\d+/[^"]+\.html)"[^>]+title="(?P<title>[^"]+)"[^>]*>.*?</a>\s*<span[^>]*>(?P<date>\d{4}-\d{2}-\d{2})</span>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = _clean_text(matched.group("title"))
        if not title:
            continue
        rows.append(
            {
                "title": title,
                "url": urljoin(MIIT_BASE_URL, matched.group("url")),
                "published_at": _parse_miit_datetime_to_iso(matched.group("date")),
            }
        )
    return rows


def _parse_miit_article_detail(payload: str, *, url: str) -> dict[str, object]:
    title = _parse_meta_content(payload, "ArticleTitle")
    return {
        "title": title,
        "url": url,
        "summary": _parse_meta_content(payload, "Description"),
        "document_no": None,
        "issuing_authority": "工业和信息化部",
        "published_at": _parse_miit_datetime_to_iso(_parse_meta_content(payload, "PubDate")),
        "attachment_urls": _extract_attachment_urls(payload),
        "content_html": None,
        "content_text": None,
    }


async def _default_loader() -> list[dict[str, object]]:
    async with httpx.AsyncClient(
        headers={"User-Agent": MIIT_USER_AGENT},
        follow_redirects=True,
        timeout=MIIT_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get(MIIT_LIST_API_URL)
        response.raise_for_status()
        rows = _parse_miit_unit_payload(response.text)

        enriched_rows: list[dict[str, object]] = []
        for row in rows[:MIIT_DETAIL_FETCH_LIMIT]:
            url = _clean_text(row.get("url"))
            if not url:
                continue
            try:
                detail_response = await client.get(url)
                detail_response.raise_for_status()
                enriched_row = _parse_miit_article_detail(detail_response.text, url=url)
                if row.get("published_at") and not enriched_row.get("published_at"):
                    enriched_row["published_at"] = row["published_at"]
                enriched_rows.append(enriched_row)
            except Exception:
                # 降级分支：详情解析失败时保留列表页标题和时间，避免整批同步被单页阻断。
                enriched_rows.append(row)
        return enriched_rows


class MiitPolicyProvider:
    source = "miit"

    def __init__(self, *, loader: Loader = _default_loader) -> None:
        self._loader = loader

    async def fetch_documents(self, *, now: datetime) -> list[PolicyDocumentSeed]:
        _ = now
        rows = await self._loader()
        documents: list[PolicyDocumentSeed] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            if not title or not url:
                continue
            documents.append(
                PolicyDocumentSeed(
                    source=self.source,
                    source_document_id=str(row.get("id") or "").strip() or None,
                    title=title,
                    summary=str(row.get("summary") or "").strip() or None,
                    document_no=str(row.get("document_no") or "").strip() or None,
                    issuing_authority=str(row.get("issuing_authority") or "").strip()
                    or "工业和信息化部",
                    policy_level=str(row.get("policy_level") or "").strip() or None,
                    category=str(row.get("category") or "").strip() or None,
                    published_at=_parse_datetime(row.get("published_at")),
                    effective_at=_parse_datetime(row.get("effective_at")),
                    url=url,
                    attachment_urls=[
                        str(item).strip()
                        for item in row.get("attachment_urls", [])
                        if str(item).strip()
                    ],
                    content_text=str(row.get("content_text") or "").strip() or None,
                    content_html=str(row.get("content_html") or "").strip() or None,
                    raw_payload=dict(row),
                )
            )
        return documents
