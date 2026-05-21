from __future__ import annotations

from urllib.parse import urlparse


def build_structured_sources(
    events: list[dict[str, object | None]],
) -> list[dict[str, object]]:
    # 来源统计只暴露稳定 provider 与计数，避免把事件内部字段耦合到前端。
    provider_counts: dict[str, int] = {}
    for event in events:
        source = str(event.get("source") or "").lower()
        scope = str(event.get("scope") or "").lower()
        event_type = str(event.get("event_type") or "").lower()
        if scope == "policy" or event_type == "policy" or source in {
            "gov_cn",
            "ndrc",
            "miit",
            "pbc",
            "csrc",
            "mofcom",
        }:
            provider = "policy_document"
        else:
            provider = "tushare" if "tushare" in source else "akshare"
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
    return [
        {"provider": provider, "count": count}
        for provider, count in sorted(provider_counts.items(), key=lambda item: item[0])
    ]


def classify_event_source_kind(event: dict[str, object | None]) -> str:
    scope = str(event.get("scope") or "").lower()
    source = str(event.get("source") or "").lower()
    event_type = str(event.get("event_type") or "").lower()
    if scope == "policy" or event_type == "policy" or source in {
        "gov_cn",
        "ndrc",
        "miit",
        "pbc",
        "csrc",
        "policy_document",
    }:
        return "policy_document"
    return "structured_event"


def build_source_items(
    *,
    events: list[dict[str, object | None]] | list[dict[str, object]],
    structured_sources: list[dict[str, object]] | None = None,
    web_sources: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    source_items: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for event in events:
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            continue
        source_kind = classify_event_source_kind(event)
        source_id = f"event-{event_id}"
        seen_ids.add(source_id)
        source_items.append(
            {
                "id": source_id,
                "source_kind": source_kind,
                "title": str(event.get("title") or event_id),
                "source_name": str(event.get("source") or "") or None,
                "quality_status": (
                    "verified"
                    if event.get("link_status") == "linked"
                    else "unavailable"
                ),
                "published_at": event.get("published_at"),
                "metadata_status": "enriched" if event.get("published_at") else "unavailable",
                "evidence_id": event_id,
            }
        )

    for index, item in enumerate(structured_sources or [], start=1):
        provider = str(item.get("provider") or "structured").strip()
        source_id = f"structured-{provider}-{index}"
        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        source_items.append(
            {
                "id": source_id,
                "source_kind": (
                    "policy_document"
                    if provider == "policy_document"
                    else "market_data"
                    if provider == "tushare"
                    else "structured_event"
                ),
                "title": f"{provider} × {item.get('count') or 0}",
                "source_name": provider,
                "quality_status": "verified",
                "metadata_status": "enriched",
            }
        )

    for index, raw_source in enumerate(web_sources or [], start=1):
        normalized = apply_web_source_fallback(dict(raw_source))
        url = str(normalized.get("url") or "").strip()
        source_id = f"web-{url or index}"
        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        metadata_status = str(normalized.get("metadata_status") or "unavailable")
        quality_status = (
            "enriched"
            if metadata_status == "enriched"
            else "domain_inferred"
            if metadata_status == "domain_inferred"
            else "unavailable"
        )
        source_items.append(
            {
                "id": source_id,
                "source_kind": "web_reference",
                "title": str(normalized.get("title") or url or "未命名联网来源"),
                "source_name": str(
                    normalized.get("source") or normalized.get("domain") or ""
                )
                or None,
                "url": url or None,
                "snippet": normalized.get("snippet"),
                "quality_status": quality_status,
                "published_at": normalized.get("published_at"),
                "domain": normalized.get("domain"),
                "metadata_status": metadata_status,
            }
        )

    source_rank = {
        "policy_document": 0,
        "structured_event": 1,
        "market_data": 2,
        "web_reference": 3,
    }
    quality_rank = {
        "verified": 0,
        "enriched": 1,
        "domain_inferred": 2,
        "unavailable": 3,
    }
    return sorted(
        source_items,
        key=lambda item: (
            source_rank.get(str(item.get("source_kind")), 9),
            quality_rank.get(str(item.get("quality_status")), 9),
            0 if item.get("published_at") else 1,
            str(item.get("title") or ""),
        ),
    )


def derive_domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def apply_web_source_fallback(raw_source: dict[str, object]) -> dict[str, object]:
    normalized = dict(raw_source)
    domain = str(normalized.get("domain") or "").strip() or derive_domain_from_url(
        str(normalized.get("url") or "").strip() or None
    )
    if domain:
        normalized["domain"] = domain
    metadata_status = str(normalized.get("metadata_status") or "").strip().lower()
    if not metadata_status:
        metadata_status = "unavailable"
        normalized["metadata_status"] = metadata_status

    if metadata_status == "unavailable":
        normalized["metadata_status"] = "unavailable"
        # 降级边界：元数据补全失败时只展示域名，避免旧 source 字段误导用户。
        normalized["source"] = domain
        normalized["published_at"] = None
    elif not normalized.get("source") and domain:
        normalized["source"] = domain
    elif "published_at" not in normalized:
        normalized["published_at"] = None
    return normalized
