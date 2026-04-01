from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import re
from html import unescape
from urllib.parse import urljoin

import httpx

from app.integrations.policy_provider import PolicyDocumentSeed


Loader = Callable[[], Awaitable[list[dict[str, object]]]]
NPC_LIST_URL = "http://www.npc.gov.cn/npc/c2/c12435/c12488/"
NPC_BASE_URL = "http://www.npc.gov.cn"
NPC_TIMEOUT_SECONDS = 30.0
NPC_DETAIL_FETCH_LIMIT = 12
NPC_USER_AGENT = (
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


def _strip_html_tags(value: str) -> str | None:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return _clean_text(text)


def _extract_div_block_by_id(payload: str, element_id: str) -> str | None:
    matched = re.search(
        rf'<div[^>]+id="{re.escape(element_id)}"[^>]*>',
        payload,
        flags=re.IGNORECASE,
    )
    if not matched:
        return None

    start = matched.start()
    index = matched.end()
    depth = 1
    while index < len(payload) and depth > 0:
        next_open = payload.find("<div", index)
        next_close = payload.find("</div>", index)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            index = next_open + 4
            continue
        depth -= 1
        index = next_close + len("</div>")

    if depth != 0:
        return None
    return payload[start:index]


def _parse_npc_datetime_to_iso(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    matched = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{1,2}))?",
        text,
    )
    if not matched:
        return None
    year, month, day, hour, minute = matched.groups()
    return (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        f"T{int(hour or '0'):02d}:{int(minute or '0'):02d}:00+08:00"
    )


def _parse_npc_list_payload(payload: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for matched in re.finditer(
        r'href="(?P<url>\.\./\.\./(?:c30834|kgfb)/[^"]+\.html)"[^>]*>(?P<title>.*?)</a>',
        payload,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = _clean_text(re.sub(r"<[^>]+>", "", matched.group("title") or ""))
        if not title:
            continue
        url = urljoin(NPC_LIST_URL, matched.group("url"))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        rows.append({"title": title, "url": url})
    return rows


def _parse_npc_article_detail(payload: str, *, url: str) -> dict[str, object]:
    title_matched = re.search(r"<h1>(?P<value>.*?)</h1>", payload, flags=re.IGNORECASE | re.DOTALL)
    source_matched = re.search(r"来源：\s*(?P<value>[^<&]+)", payload)
    date_matched = re.search(r'var fbrq = "(?P<value>[^"]+)"', payload)
    content_block = _extract_div_block_by_id(payload, "Zoom")
    content_html = content_block.strip() if content_block else None
    content_text = _strip_html_tags(content_html or "")
    summary = content_text[:140].strip() if content_text else None

    return {
        "title": _clean_text(title_matched.group("value")) if title_matched else None,
        "url": url,
        "summary": summary,
        "document_no": None,
        "issuing_authority": _clean_text(source_matched.group("value")) if source_matched else "国家法律法规数据库",
        "published_at": _parse_npc_datetime_to_iso(date_matched.group("value") if date_matched else None),
        "attachment_urls": [],
        "content_html": content_html,
        "content_text": content_text,
    }


async def _default_loader() -> list[dict[str, object]]:
    async with httpx.AsyncClient(
        headers={"User-Agent": NPC_USER_AGENT},
        follow_redirects=True,
        timeout=NPC_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get(NPC_LIST_URL)
        response.raise_for_status()
        rows = _parse_npc_list_payload(response.text)

        enriched_rows: list[dict[str, object]] = []
        for row in rows[:NPC_DETAIL_FETCH_LIMIT]:
            url = _clean_text(row.get("url"))
            if not url:
                continue
            try:
                detail_response = await client.get(url)
                detail_response.raise_for_status()
                enriched_rows.append(_parse_npc_article_detail(detail_response.text, url=url))
            except Exception:
                # 降级分支：单条详情失败时保留列表结果，避免整批同步被单页阻断。
                enriched_rows.append(row)
        return enriched_rows


class NpcPolicyProvider:
    source = "npc"

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
                    or "国家法律法规数据库",
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
