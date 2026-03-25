from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.web_source_metadata_cache import WebSourceMetadataCache


DOMAIN_SOURCE_MAP: dict[str, str] = {
    "reuters.com": "Reuters",
    "finance.eastmoney.com": "东方财富",
    "eastmoney.com": "东方财富",
    "cls.cn": "财联社",
    "stcn.com": "证券时报",
    "cninfo.com.cn": "巨潮资讯",
}


def _normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        hostname = urlparse(url).hostname
    except ValueError:
        return None
    if not hostname:
        return None
    normalized = hostname.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized or None


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    text = str(url).strip()
    if not text.startswith(("http://", "https://")):
        # 非 HTTP/HTTPS 直接拒绝，避免解析本地/私有协议。
        return None
    return text


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _extract_meta_content(html: str, *, attr_name: str, attr_value: str) -> str | None:
    pattern = re.compile(
        rf"<meta[^>]+{attr_name}=[\"']{re.escape(attr_value)}[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    )
    match = pattern.search(html)
    if match:
        return match.group(1).strip()

    reverse_pattern = re.compile(
        rf"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+{attr_name}=[\"']{re.escape(attr_value)}[\"']",
        re.IGNORECASE,
    )
    reverse_match = reverse_pattern.search(html)
    if reverse_match:
        return reverse_match.group(1).strip()
    return None


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def _extract_json_ld_objects(html: str) -> list[dict[str, Any]]:
    matches = re.findall(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    results: list[dict[str, Any]] = []
    for raw_match in matches:
        normalized = raw_match.strip()
        if not normalized:
            continue
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            results.append(parsed)
        elif isinstance(parsed, list):
            results.extend(item for item in parsed if isinstance(item, dict))
    return results


def _find_json_ld_value(payload: Any, key: str) -> str | None:
    if isinstance(payload, dict):
        if key in payload and isinstance(payload[key], str):
            value = payload[key].strip()
            if value:
                return value
        for nested_value in payload.values():
            found = _find_json_ld_value(nested_value, key)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_json_ld_value(item, key)
            if found:
                return found
    return None


def _resolve_source_from_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    if domain in DOMAIN_SOURCE_MAP:
        return DOMAIN_SOURCE_MAP[domain]
    for known_domain, source in DOMAIN_SOURCE_MAP.items():
        if domain.endswith(f".{known_domain}"):
            return source
    return domain


def _parse_datetime_text(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None

    for candidate in (
        normalized,
        normalized.replace("Z", "+00:00"),
        normalized.replace("/", "-"),
    ):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _extract_page_metadata(html: str, domain: str | None) -> dict[str, Any]:
    json_ld_objects = _extract_json_ld_objects(html)

    title = (
        _extract_meta_content(html, attr_name="property", attr_value="og:title")
        or _extract_title(html)
    )
    source = (
        _extract_meta_content(html, attr_name="property", attr_value="og:site_name")
        or _find_json_ld_value(json_ld_objects, "name")
        or _extract_meta_content(html, attr_name="name", attr_value="application-name")
        or _resolve_source_from_domain(domain)
    )
    published_at = (
        _extract_meta_content(html, attr_name="property", attr_value="article:published_time")
        or _extract_meta_content(html, attr_name="property", attr_value="og:published_time")
        or _find_json_ld_value(json_ld_objects, "datePublished")
        or _extract_meta_content(html, attr_name="name", attr_value="pubdate")
        or _extract_meta_content(html, attr_name="name", attr_value="publishdate")
        or _extract_meta_content(html, attr_name="name", attr_value="date")
    )
    if not published_at:
        time_match = re.search(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", html, re.IGNORECASE)
        if time_match:
            published_at = time_match.group(1).strip()

    resolved_published_at = _parse_datetime_text(published_at)
    # metadata_status 仅表示解析质量，不代表内容可信度。
    metadata_status = "enriched" if resolved_published_at or (source and source != domain) else "domain_inferred"

    return {
        "resolved_title": title,
        "resolved_source": source,
        "resolved_domain": domain,
        "resolved_published_at": resolved_published_at,
        "metadata_status": metadata_status,
    }


async def _load_cached_metadata(
    session: AsyncSession,
    *,
    normalized_url: str,
    url_hash: str,
    now: datetime,
) -> WebSourceMetadataCache | None:
    # 仅返回未过期缓存，避免过期数据影响来源展示。
    statement = (
        select(WebSourceMetadataCache)
        .where(WebSourceMetadataCache.url_hash == url_hash)
        .where(WebSourceMetadataCache.url == normalized_url)
        .where(WebSourceMetadataCache.expires_at >= now)
        .order_by(WebSourceMetadataCache.fetched_at.desc())
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def _upsert_metadata_cache(
    session: AsyncSession,
    *,
    normalized_url: str,
    url_hash: str,
    metadata: dict[str, Any],
    now: datetime,
    success_ttl_seconds: int,
    failure_ttl_seconds: int,
) -> WebSourceMetadataCache:
    row = await _load_cached_metadata(
        session,
        normalized_url=normalized_url,
        url_hash=url_hash,
        now=datetime(1970, 1, 1, tzinfo=UTC),
    )
    if row is None:
        row = WebSourceMetadataCache(url=normalized_url, url_hash=url_hash, expires_at=now)
        session.add(row)

    row.resolved_title = metadata.get("resolved_title")
    row.resolved_source = metadata.get("resolved_source")
    row.resolved_domain = metadata.get("resolved_domain")
    row.resolved_published_at = metadata.get("resolved_published_at")
    row.metadata_status = str(metadata.get("metadata_status") or "unavailable")
    row.fetched_at = now
    # 成功与失败使用不同 TTL，避免失败缓存长期阻塞重试。
    ttl_seconds = (
        success_ttl_seconds
        if row.metadata_status == "enriched"
        else failure_ttl_seconds
    )
    row.expires_at = now + timedelta(seconds=ttl_seconds)
    return row


def _merge_source_item(
    raw_source: dict[str, Any],
    *,
    domain: str | None,
    metadata_status: str,
    resolved_title: str | None,
    resolved_source: str | None,
    resolved_published_at: datetime | None,
) -> dict[str, Any]:
    return {
        "title": raw_source.get("title") or resolved_title,
        "url": raw_source.get("url"),
        "source": raw_source.get("source") or resolved_source or domain,
        "published_at": (
            raw_source.get("published_at")
            or (resolved_published_at.isoformat() if resolved_published_at else None)
        ),
        "snippet": raw_source.get("snippet"),
        "domain": raw_source.get("domain") or domain,
        "metadata_status": raw_source.get("metadata_status") or metadata_status,
    }


async def enrich_web_sources(
    *,
    session: AsyncSession,
    raw_sources: list[dict[str, Any]],
    http_client: httpx.AsyncClient | None = None,
    timeout_seconds: int = 3,
    success_ttl_seconds: int = 86400,
    failure_ttl_seconds: int = 7200,
    max_bytes: int = 1024 * 512,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    owns_client = http_client is None
    # 解析来源元数据时使用短超时，避免阻塞分析主链路。
    client = http_client or httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={
            "User-Agent": "StockProjectCitationResolver/1.0",
        },
    )

    try:
        enriched_sources: list[dict[str, Any]] = []
        for raw_source in raw_sources:
            normalized_url = _normalize_url(str(raw_source.get("url") or ""))
            domain = _normalize_domain(normalized_url)
            if not normalized_url:
                enriched_sources.append(
                    _merge_source_item(
                        raw_source,
                        domain=domain,
                        metadata_status="unavailable",
                        resolved_title=None,
                        resolved_source=_resolve_source_from_domain(domain),
                        resolved_published_at=None,
                    )
                )
                continue

            url_hash = _hash_url(normalized_url)
            cached_row = await _load_cached_metadata(
                session,
                normalized_url=normalized_url,
                url_hash=url_hash,
                now=now,
            )
            if cached_row is not None:
                enriched_sources.append(
                    _merge_source_item(
                        raw_source,
                        domain=cached_row.resolved_domain or domain,
                        metadata_status=cached_row.metadata_status,
                        resolved_title=cached_row.resolved_title,
                        resolved_source=cached_row.resolved_source,
                        resolved_published_at=cached_row.resolved_published_at,
                    )
                )
                continue

            metadata = {
                "resolved_title": None,
                "resolved_source": _resolve_source_from_domain(domain),
                "resolved_domain": domain,
                "resolved_published_at": None,
                "metadata_status": "unavailable",
            }

            try:
                response = await client.get(normalized_url)
                content_type = str(response.headers.get("content-type", "")).lower()
                if response.status_code >= 400:
                    raise RuntimeError(f"unexpected status: {response.status_code}")
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    # 非 HTML 资源不解析正文，直接回退为域名来源。
                    raise RuntimeError("non-html response")

                content_bytes = response.content[:max_bytes]
                html = content_bytes.decode(response.encoding or "utf-8", errors="ignore")
                metadata = _extract_page_metadata(html, domain)
            except Exception:
                if domain:
                    # 失败时回退为域名来源，避免返回空对象。
                    metadata = {
                        "resolved_title": raw_source.get("title"),
                        "resolved_source": _resolve_source_from_domain(domain),
                        "resolved_domain": domain,
                        "resolved_published_at": None,
                        "metadata_status": "unavailable",
                    }

            cached_row = await _upsert_metadata_cache(
                session,
                normalized_url=normalized_url,
                url_hash=url_hash,
                metadata=metadata,
                now=now,
                success_ttl_seconds=success_ttl_seconds,
                failure_ttl_seconds=failure_ttl_seconds,
            )
            enriched_sources.append(
                _merge_source_item(
                    raw_source,
                    domain=cached_row.resolved_domain or domain,
                    metadata_status=cached_row.metadata_status,
                    resolved_title=cached_row.resolved_title,
                    resolved_source=cached_row.resolved_source,
                    resolved_published_at=cached_row.resolved_published_at,
                )
            )

        await session.flush()
        return enriched_sources
    finally:
        if owns_client:
            await client.aclose()
