from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import re
from html import unescape
from urllib.parse import urljoin

import httpx

from app.integrations.policy_provider import PolicyDocumentSeed


Loader = Callable[[], Awaitable[list[dict[str, object]]]] 
CSRC_LIST_URL = "https://www.csrc.gov.cn/csrc/c100028/common_list.shtml"
CSRC_BASE_URL = "https://www.csrc.gov.cn"
CSRC_TIMEOUT_SECONDS = 30.0
CSRC_DETAIL_FETCH_LIMIT = 12
CSRC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
CSRC_POLICY_TITLE_KEYWORDS = (
    "征求意见",
    "办法",
    "规定",
    "规则",
    "制度",
    "通知",
    "意见",
    "实施办法",
    "公开征求意见",
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


def _parse_meta_content(payload: str, meta_name: str) -> str | None:
    matched = re.search(
        rf'<meta[^>]+name=["\']{re.escape(meta_name)}["\'][^>]+content=["\'](?P<value>[^"\']*)["\']',
        payload,
        flags=re.IGNORECASE,
    )
    if not matched:
        return None
    return _clean_text(matched.group("value"))


def _parse_csrc_datetime_to_iso(value: str | None) -> str | None:
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


def _parse_csrc_list_payload(payload: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for matched in re.finditer(
        r'href="(?P<url>/csrc/c100028/c\d+/content\.shtml)"[^>]*>(?P<title>.*?)</a>',
        payload,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = _clean_text(re.sub(r"<[^>]+>", "", matched.group("title") or ""))
        if not title or not any(keyword in title for keyword in CSRC_POLICY_TITLE_KEYWORDS):
            continue
        url = urljoin(CSRC_BASE_URL, matched.group("url"))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        rows.append({"title": title, "url": url})
    return rows


def _parse_csrc_article_detail(payload: str, *, url: str) -> dict[str, object]:
    return {
        "title": _parse_meta_content(payload, "ArticleTitle"),
        "url": url,
        "summary": _parse_meta_content(payload, "Description"),
        "document_no": None,
        "issuing_authority": _parse_meta_content(payload, "ContentSource") or "中国证监会",
        "published_at": _parse_csrc_datetime_to_iso(_parse_meta_content(payload, "PubDate")),
        "attachment_urls": [],
        "content_html": None,
        "content_text": None,
    }


async def _default_loader() -> list[dict[str, object]]:
    async with httpx.AsyncClient(
        headers={"User-Agent": CSRC_USER_AGENT},
        follow_redirects=True,
        timeout=CSRC_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get(CSRC_LIST_URL)
        response.raise_for_status()
        rows = _parse_csrc_list_payload(response.text)

        enriched_rows: list[dict[str, object]] = []
        for row in rows[:CSRC_DETAIL_FETCH_LIMIT]:
            url = _clean_text(row.get("url"))
            if not url:
                continue
            try:
                detail_response = await client.get(url)
                detail_response.raise_for_status()
                enriched_rows.append(_parse_csrc_article_detail(detail_response.text, url=url))
            except Exception:
                # 降级分支：详情抓取失败时保留列表结果，避免整批政策同步被单页阻断。
                enriched_rows.append(row)
        return enriched_rows


class CsrcPolicyProvider:
    source = "csrc"

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
                    or "中国证监会",
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
