from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import json
import re
from html import unescape
from urllib.parse import urljoin

import httpx

from app.integrations.policy_provider import PolicyDocumentSeed


Loader = Callable[[], Awaitable[list[dict[str, object]]]]
GOV_CN_FEED_URL = "https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json"
GOV_CN_TIMEOUT_SECONDS = 30.0
GOV_CN_DETAIL_FETCH_LIMIT = 12
GOV_CN_USER_AGENT = (
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
    normalized = re.sub(r"\n{2,}", "\n", text)
    return _clean_text(normalized)


def _parse_cn_date_to_iso(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None

    matched = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})", text)
    if not matched:
        return None
    year, month, day = matched.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T00:00:00+08:00"


def _extract_table_value(payload: str, label: str) -> str | None:
    matched = re.search(
        rf"<b>\s*{re.escape(label)}\s*：</b>\s*</td>\s*<td[^>]*>(?P<value>.*?)</td>",
        payload,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not matched:
        return None
    return _clean_text(_strip_html_tags(matched.group("value") or ""))


def _extract_content_html(payload: str) -> str | None:
    matched = re.search(
        r'<div class="trs_editor_view[^"]*">(?P<content>.*?)</div>',
        payload,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not matched:
        return None
    content = matched.group("content") or ""
    return content.strip() or None


def _extract_summary_from_content(content_text: str | None) -> str | None:
    if not content_text:
        return None
    return content_text[:140].strip() or None


def _parse_gov_cn_feed_payload(payload: str) -> list[dict[str, object]]:
    data = json.loads(payload)
    if not isinstance(data, list):
        return []

    rows: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("TITLE"))
        url = _clean_text(item.get("URL"))
        if not title or not url:
            continue
        rows.append(
            {
                "id": _clean_text(item.get("DOCID")) or _clean_text(item.get("id")),
                "title": title,
                "summary": _clean_text(item.get("SUB_TITLE")),
                "url": url,
                "published_at": _parse_cn_date_to_iso(_clean_text(item.get("DOCRELPUBTIME"))),
            }
        )
    return rows


def _parse_gov_cn_article_detail(
    payload: str,
    *,
    fallback_row: dict[str, object],
) -> dict[str, object]:
    content_html = _extract_content_html(payload)
    content_text = _strip_html_tags(content_html or "")
    summary = _clean_text(fallback_row.get("summary")) or _extract_summary_from_content(content_text)

    return {
        **fallback_row,
        "issuing_authority": _extract_table_value(payload, "发文机关") or "国务院",
        "document_no": _extract_table_value(payload, "发文字号"),
        "published_at": _parse_cn_date_to_iso(_extract_table_value(payload, "发布日期"))
        or fallback_row.get("published_at"),
        "effective_at": _parse_cn_date_to_iso(_extract_table_value(payload, "成文日期")),
        "summary": summary,
        "content_html": content_html,
        "content_text": content_text,
    }


async def _default_loader() -> list[dict[str, object]]:
    async with httpx.AsyncClient(
        headers={"User-Agent": GOV_CN_USER_AGENT},
        follow_redirects=True,
        timeout=GOV_CN_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get(GOV_CN_FEED_URL)
        response.raise_for_status()
        rows = _parse_gov_cn_feed_payload(response.text)

        enriched_rows: list[dict[str, object]] = []
        for row in rows[:GOV_CN_DETAIL_FETCH_LIMIT]:
            url = _clean_text(row.get("url"))
            if not url:
                continue
            try:
                detail_response = await client.get(url)
                detail_response.raise_for_status()
                enriched_rows.append(
                    _parse_gov_cn_article_detail(detail_response.text, fallback_row=row)
                )
            except Exception:
                # 降级分支：单条详情解析失败时保留列表元数据，避免整批政策同步直接中断。
                enriched_rows.append(row)
        return enriched_rows


class GovCnPolicyProvider:
    source = "gov_cn"

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
                    issuing_authority="国务院",
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
