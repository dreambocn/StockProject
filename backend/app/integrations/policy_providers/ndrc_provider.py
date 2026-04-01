from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import re
from html import unescape
from urllib.parse import urljoin

import httpx

from app.integrations.policy_provider import PolicyDocumentSeed


Loader = Callable[[], Awaitable[list[dict[str, object]]]]
NDRC_LIST_URL = "https://www.ndrc.gov.cn/xxgk/zcfb/tz/"
NDRC_BASE_URL = "https://www.ndrc.gov.cn"
NDRC_TIMEOUT_SECONDS = 30.0
NDRC_DETAIL_FETCH_LIMIT = 12
NDRC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
POLICY_TITLE_KEYWORDS = ("通知", "意见", "办法", "方案", "决定", "公告", "实施")


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


def _strip_html_tags(value: str) -> str | None:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return _clean_text(text)


def _parse_ndrc_datetime_to_iso(value: str | None) -> str | None:
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


def _extract_document_no_from_title(title: str | None) -> str | None:
    text = _clean_text(title)
    if not text:
        return None
    matched = re.search(r"\(([^()]*〔\d{4}〕[^()]*号)\)", text)
    if matched:
        return _clean_text(matched.group(1))
    return None


def _extract_content_html(payload: str) -> str | None:
    matched = re.search(
        r'<div class="TRS_Editor">(?P<content>.*?)</div>',
        payload,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not matched:
        return None
    content = matched.group("content") or ""
    return content.strip() or None


def _extract_attachment_urls(payload: str, *, url: str) -> list[str]:
    attachment_urls: list[str] = []
    for matched in re.finditer(
        r'href="(?P<value>[^"]+\.(?:pdf|doc|docx|xls|xlsx|zip))"',
        payload,
        flags=re.IGNORECASE,
    ):
        attachment_url = urljoin(url, matched.group("value"))
        if attachment_url not in attachment_urls:
            attachment_urls.append(attachment_url)
    return attachment_urls


def _parse_ndrc_list_payload(payload: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for matched in re.finditer(
        r'href="(?P<url>\./[^"]+\.html)"[^>]*>(?P<title>.*?)</a>',
        payload,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = _strip_html_tags(matched.group("title") or "")
        if not title or not any(keyword in title for keyword in POLICY_TITLE_KEYWORDS):
            continue
        url = urljoin(NDRC_LIST_URL, matched.group("url"))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        rows.append({"title": title, "url": url})
    return rows


def _parse_ndrc_article_detail(payload: str, *, url: str) -> list[dict[str, object]] | dict[str, object]:
    title = _parse_meta_content(payload, "ArticleTitle")
    content_html = _extract_content_html(payload)
    content_text = _strip_html_tags(content_html or "")
    summary = _parse_meta_content(payload, "Description") or (
        content_text[:140].strip() if content_text else None
    )
    return {
        "title": title,
        "url": url,
        "summary": summary,
        "document_no": _extract_document_no_from_title(title),
        "issuing_authority": "国家发展改革委",
        "published_at": _parse_ndrc_datetime_to_iso(_parse_meta_content(payload, "PubDate")),
        "attachment_urls": _extract_attachment_urls(payload, url=url),
        "content_html": content_html,
        "content_text": content_text,
    }


async def _default_loader() -> list[dict[str, object]]:
    async with httpx.AsyncClient(
        headers={"User-Agent": NDRC_USER_AGENT},
        follow_redirects=True,
        timeout=NDRC_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get(NDRC_LIST_URL)
        response.raise_for_status()
        rows = _parse_ndrc_list_payload(response.text)

        enriched_rows: list[dict[str, object]] = []
        for row in rows[:NDRC_DETAIL_FETCH_LIMIT]:
            url = _clean_text(row.get("url"))
            if not url:
                continue
            try:
                detail_response = await client.get(url)
                detail_response.raise_for_status()
                enriched_rows.append(_parse_ndrc_article_detail(detail_response.text, url=url))
            except Exception:
                # 降级分支：单条详情失败时保留列表结果，避免整批同步被单条页面阻断。
                enriched_rows.append(row)
        return enriched_rows


class NdrcPolicyProvider:
    source = "ndrc"

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
                    or "国家发展改革委",
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
