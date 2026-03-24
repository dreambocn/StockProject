import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.schemas.analysis import (
    AnalysisEventLinkResponse,
    AnalysisReportArchiveItemResponse,
    AnalysisReportResponse,
    StockAnalysisSummaryResponse,
)
from app.schemas.stocks import (
    StockDailySnapshotResponse,
    StockInstrumentResponse,
)
from app.services.analysis_repository import (
    build_analysis_key,
    create_analysis_report,
    create_analysis_session_record,
    load_active_session_by_key,
    load_analysis_events,
    load_analysis_session,
    load_latest_report,
    load_latest_snapshot,
    load_latest_fresh_report,
    load_price_window_rows,
    load_recent_news_events,
    load_stock_instrument,
    list_analysis_reports,
    upsert_analysis_event_link,
    update_analysis_report_web_sources,
)
from app.services.analysis_runtime_service import (
    cache_active_session_id,
    cache_fresh_report_id,
    clear_cached_active_session_id,
    event_bus,
    get_analysis_lock,
)
from app.services.event_link_service import build_event_link_result
from app.services.factor_weight_service import calculate_factor_weights
from app.services.key_event_extraction_service import extract_key_event_types
from app.services.llm_analysis_service import generate_stock_analysis_report
from app.services.news_sentiment_service import analyze_news_sentiment
from app.services.web_source_metadata_service import enrich_web_sources


class AnalysisNotFoundError(Exception):
    pass


def _derive_status(
    report_status: str | None, event_count: int
) -> Literal["ready", "partial", "pending"]:
    if report_status == "ready":
        return "ready"
    if report_status == "partial":
        return "partial"
    if event_count > 0:
        return "partial"
    return "pending"


def _resolve_event_type(*, scope: str, source: str, event_tags: list[str]) -> str:
    if scope == "policy" or "policy" in event_tags or "regulation" in event_tags:
        return "policy"
    if source == "cninfo_announcement" or "announcement" in event_tags:
        return "announcement"
    return "news"


def _build_structured_sources(events: list[dict[str, object | None]]) -> list[dict[str, object]]:
    provider_counts: dict[str, int] = {}
    for event in events:
        source = str(event.get("source") or "").lower()
        provider = "tushare" if "tushare" in source else "akshare"
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
    return [
        {"provider": provider, "count": count}
        for provider, count in sorted(provider_counts.items(), key=lambda item: item[0])
    ]


def _derive_domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def _apply_web_source_fallback(raw_source: dict[str, object]) -> dict[str, object]:
    normalized = dict(raw_source)
    domain = str(normalized.get("domain") or "").strip() or _derive_domain_from_url(
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
        # 关键流程：当元数据补全失败时，输出必须严格回落为 domain 来源，避免遗留旧 source 误导前端。
        normalized["source"] = domain
        normalized["published_at"] = None
    elif not normalized.get("source") and domain:
        normalized["source"] = domain
    elif "published_at" not in normalized:
        normalized["published_at"] = None

    if "published_at" not in normalized:
        normalized["published_at"] = None
    return normalized


def _needs_web_source_enrichment(raw_source: dict[str, object]) -> bool:
    metadata_status = str(raw_source.get("metadata_status") or "").strip().lower()
    return bool(raw_source.get("url")) and (
        not raw_source.get("source")
        or not raw_source.get("published_at")
        or not raw_source.get("domain")
        or metadata_status in {"", "unavailable", "domain_inferred"}
    )


async def _backfill_report_web_sources(
    session: AsyncSession,
    *,
    report_obj: object | None,
    per_report_limit: int,
    remaining_budget: int,
) -> tuple[list[dict[str, object]], int]:
    raw_sources = [
        _apply_web_source_fallback(dict(item))
        for item in (getattr(report_obj, "web_sources", None) or [])
        if isinstance(item, dict)
    ]
    if report_obj is None or not raw_sources or remaining_budget <= 0:
        return raw_sources, remaining_budget

    target_indexes = [
        index
        for index, item in enumerate(raw_sources)
        if _needs_web_source_enrichment(item)
    ][: min(per_report_limit, remaining_budget)]
    if not target_indexes:
        return raw_sources, remaining_budget

    settings = get_settings()
    target_sources = [raw_sources[index] for index in target_indexes]
    try:
        enriched_sources = await enrich_web_sources(
            session=session,
            raw_sources=target_sources,
            timeout_seconds=settings.web_source_metadata_timeout_seconds,
            success_ttl_seconds=settings.web_source_metadata_cache_ttl_seconds,
            failure_ttl_seconds=settings.web_source_metadata_failure_ttl_seconds,
            max_bytes=settings.web_source_metadata_max_bytes,
        )
    except Exception:
        enriched_sources = target_sources

    next_sources = list(raw_sources)
    changed = False
    for index, enriched in zip(target_indexes, enriched_sources, strict=False):
        normalized = _apply_web_source_fallback(dict(enriched))
        if normalized != next_sources[index]:
            next_sources[index] = normalized
            changed = True

    if changed:
        await update_analysis_report_web_sources(
            session,
            report=report_obj,
            web_sources=next_sources,
        )
        await session.commit()

    return next_sources, remaining_budget - len(target_indexes)


def _serialize_report(
    report_obj: object | None,
) -> dict[str, object] | None:
    if report_obj is None:
        return None

    report = AnalysisReportResponse.model_validate(
        {
            "id": getattr(report_obj, "id", None),
            "status": getattr(report_obj, "status", "pending") or "pending",
            "summary": getattr(report_obj, "summary", ""),
            "risk_points": getattr(report_obj, "risk_points", None) or [],
            "factor_breakdown": getattr(report_obj, "factor_breakdown", None) or [],
            "generated_at": getattr(report_obj, "generated_at", None),
            "topic": getattr(report_obj, "topic", None),
            "published_from": getattr(report_obj, "published_from", None),
            "published_to": getattr(report_obj, "published_to", None),
            "trigger_source": getattr(report_obj, "trigger_source", "manual"),
            "anchor_event_id": getattr(report_obj, "anchor_event_id", None),
            "anchor_event_title": getattr(report_obj, "anchor_event_title", None),
            "used_web_search": getattr(report_obj, "used_web_search", False),
            "web_search_status": getattr(report_obj, "web_search_status", "disabled"),
            "session_id": getattr(report_obj, "session_id", None),
            "started_at": getattr(report_obj, "started_at", None),
            "completed_at": getattr(report_obj, "completed_at", None),
            "content_format": getattr(report_obj, "content_format", "markdown"),
            "structured_sources": getattr(report_obj, "structured_sources", None) or [],
            "web_sources": getattr(report_obj, "web_sources", None) or [],
        }
    )
    return report.model_dump()


def serialize_report_archive_item(report_obj: object) -> dict[str, object]:
    return AnalysisReportArchiveItemResponse.model_validate(
        _serialize_report(report_obj)
    ).model_dump()


async def get_stock_analysis_summary(
    session: AsyncSession,
    ts_code: str,
    *,
    topic: str | None = None,
    event_id: str | None = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    event_limit: int = 20,
) -> dict[str, object | None]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await load_stock_instrument(session, normalized_ts_code)
    snapshot = await load_latest_snapshot(session, normalized_ts_code)
    persisted_events = await load_analysis_events(
        session,
        normalized_ts_code,
        limit=event_limit,
        anchor_event_id=event_id,
    )
    persisted_report = await load_latest_report(
        session,
        normalized_ts_code,
        topic=topic,
        anchor_event_id=event_id,
    )
    event_context_status: Literal["direct", "topic_fallback", "none"] = "none"
    event_context_message: str | None = None
    if event_id and persisted_report is None:
        persisted_report = await load_latest_report(
            session,
            normalized_ts_code,
            topic=topic,
            anchor_event_id=None,
        )
        event_context_status = "topic_fallback"
        event_context_message = "未找到指定锚点事件，已回退到主题级分析"
    elif event_id:
        event_context_status = "direct"

    if persisted_report is not None:
        enriched_web_sources, _remaining_budget = await _backfill_report_web_sources(
            session,
            report_obj=persisted_report,
            per_report_limit=5,
            remaining_budget=5,
        )
        persisted_report.web_sources = enriched_web_sources

    instrument_obj = (
        StockInstrumentResponse.model_validate(instrument) if instrument else None
    )
    snapshot_obj = (
        StockDailySnapshotResponse.model_validate(snapshot) if snapshot else None
    )
    instrument_payload = instrument_obj.model_dump() if instrument_obj else None
    snapshot_payload = snapshot_obj.model_dump() if snapshot_obj else None
    validated_events = [
        AnalysisEventLinkResponse.model_validate(item) for item in persisted_events
    ]
    event_payloads = [event.model_dump() for event in validated_events]
    report_payload = _serialize_report(persisted_report)
    status = _derive_status(
        getattr(persisted_report, "status", None) if persisted_report else None,
        len(event_payloads),
    )

    resolved_topic = topic
    resolved_published_from = published_from
    resolved_published_to = published_to
    generated_at = (
        getattr(persisted_report, "generated_at", None)
        if persisted_report
        else None
    )
    if persisted_report is not None:
        resolved_topic = persisted_report.topic
        resolved_published_from = persisted_report.published_from
        resolved_published_to = persisted_report.published_to

    result = {
        "ts_code": normalized_ts_code,
        "instrument": instrument_payload,
        "latest_snapshot": snapshot_payload,
        "status": status,
        "generated_at": generated_at,
        "topic": resolved_topic,
        "event_context_status": event_context_status,
        "event_context_message": event_context_message,
        "published_from": resolved_published_from,
        "published_to": resolved_published_to,
        "event_count": len(event_payloads),
        "events": event_payloads,
        "report": report_payload,
    }
    StockAnalysisSummaryResponse.model_validate(result)
    return result


async def list_stock_analysis_report_archives(
    session: AsyncSession, ts_code: str, *, topic: str | None = None, event_id: str | None = None, limit: int
) -> dict[str, object]:
    normalized_ts_code = ts_code.strip().upper()
    reports = await list_analysis_reports(
        session,
        ts_code=normalized_ts_code,
        topic=topic,
        anchor_event_id=event_id,
        limit=limit,
    )
    remaining_budget = 10
    for index, report in enumerate(reports):
        if index >= 3 or remaining_budget <= 0:
            break
        enriched_web_sources, remaining_budget = await _backfill_report_web_sources(
            session,
            report_obj=report,
            per_report_limit=3,
            remaining_budget=remaining_budget,
        )
        report.web_sources = enriched_web_sources
    return {
        "ts_code": normalized_ts_code,
        "items": [serialize_report_archive_item(report) for report in reports],
    }


async def start_analysis_session(
    session: AsyncSession,
    ts_code: str,
    *,
    topic: str | None,
    event_id: str | None,
    force_refresh: bool,
    use_web_search: bool,
    trigger_source: str,
    execute_inline: bool = False,
) -> dict[str, object]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await load_stock_instrument(session, normalized_ts_code)
    if instrument is None:
        raise AnalysisNotFoundError("stock not found")

    settings = get_settings()
    analysis_key = build_analysis_key(
        ts_code=normalized_ts_code,
        topic=topic,
        anchor_event_id=event_id,
        use_web_search=use_web_search,
        trigger_source=trigger_source,
    )
    lock = await get_analysis_lock(analysis_key)
    async with lock:
        # 关键流程：历史报告按股票/主题维度做 1 小时冷却，优先级高于 force_refresh。
        # 这样可以避免用户重复点击刷新或不同来源重复触发时，在短时间内写入多份归档报告。
        fresh_report = await load_latest_fresh_report(
            session,
            ts_code=normalized_ts_code,
            topic=topic,
            anchor_event_id=event_id,
            freshness_minutes=settings.analysis_report_freshness_minutes,
        )
        if fresh_report is not None:
            return {
                "session_id": None,
                "report_id": fresh_report.id,
                "status": "completed",
                "reused": False,
                "cached": True,
            }

        active_after = datetime.now(UTC) - timedelta(
            seconds=settings.analysis_active_session_ttl_seconds
        )
        active_session = await load_active_session_by_key(
            session,
            analysis_key=analysis_key,
            active_after=active_after,
        )
        if active_session is not None:
            await cache_active_session_id(
                analysis_key,
                active_session.id,
                settings.analysis_active_session_ttl_seconds,
            )
            return {
                "session_id": active_session.id,
                "report_id": active_session.report_id,
                "status": active_session.status,
                "reused": True,
                "cached": False,
            }

        session_row = await create_analysis_session_record(
            session,
            analysis_key=analysis_key,
            ts_code=normalized_ts_code,
            topic=topic,
            anchor_event_id=event_id,
            use_web_search=use_web_search,
            trigger_source=trigger_source,
        )
        await session.commit()
        await session.refresh(session_row)
        await cache_active_session_id(
            analysis_key,
            session_row.id,
            settings.analysis_active_session_ttl_seconds,
        )

    if execute_inline:
        await run_analysis_session_by_id(session_row.id)
    else:
        asyncio.create_task(run_analysis_session_by_id(session_row.id))

    return {
        "session_id": session_row.id,
        "report_id": None,
        "status": session_row.status,
        "reused": False,
        "cached": False,
    }


async def run_analysis_session_by_id(session_id: str) -> None:
    async with SessionLocal() as session:
        session_row = await load_analysis_session(session, session_id)
        if session_row is None:
            return

        analysis_key = session_row.analysis_key
        try:
            session_row.status = "running"
            session_row.started_at = session_row.started_at or datetime.now(UTC)
            session_row.error_message = None
            await session.commit()
            await event_bus.publish(
                session_id,
                "status",
                {"session_id": session_id, "status": "running"},
            )

            instrument = await load_stock_instrument(session, session_row.ts_code)
            if instrument is None:
                raise AnalysisNotFoundError("stock not found")

            raw_events = await load_recent_news_events(
                session,
                session_row.ts_code,
                topic=session_row.topic,
                anchor_event_id=session_row.anchor_event_id,
                published_from=None,
                published_to=None,
                limit=20,
            )
            event_payloads: list[dict[str, object | None]] = []

            # 关键流程：事件增强只在生成会话里执行，避免 summary 只读查询产生副作用。
            for raw_event in raw_events:
                sentiment = analyze_news_sentiment(raw_event.title, raw_event.summary)
                event_tags = extract_key_event_types(raw_event.title, raw_event.summary)
                event_type = _resolve_event_type(
                    scope=raw_event.scope,
                    source=raw_event.source,
                    event_tags=event_tags,
                )
                price_window = await load_price_window_rows(
                    session,
                    session_row.ts_code,
                    anchor_from=(
                        raw_event.published_at.date() if raw_event.published_at else None
                    ),
                )

                raw_event.event_type = event_type
                raw_event.sentiment_label = sentiment.label
                raw_event.sentiment_score = sentiment.score
                raw_event.event_tags = ",".join(event_tags)
                raw_event.analysis_status = "ready" if price_window else "partial"

                if price_window:
                    link_result = build_event_link_result(
                        price_window,
                        sentiment_score=sentiment.score,
                        label_count=len(event_tags),
                    )
                    anchor_trade_date = price_window[0]["trade_date"]
                    await upsert_analysis_event_link(
                        session,
                        event_id=raw_event.id,
                        ts_code=session_row.ts_code,
                        anchor_trade_date=anchor_trade_date,
                        window_return_pct=link_result.window_return_pct,
                        window_volatility=link_result.window_volatility,
                        abnormal_volume_ratio=link_result.abnormal_volume_ratio,
                        correlation_score=link_result.correlation_score,
                        confidence=link_result.confidence,
                        link_status=link_result.link_status,
                    )
                    event_payloads.append(
                        AnalysisEventLinkResponse.model_validate(
                            {
                                "event_id": raw_event.id,
                                "scope": raw_event.scope,
                                "title": raw_event.title,
                                "published_at": raw_event.published_at,
                                "source": raw_event.source,
                                "macro_topic": raw_event.macro_topic,
                                "event_type": event_type,
                                "event_tags": event_tags,
                                "sentiment_label": sentiment.label,
                                "sentiment_score": sentiment.score,
                                "anchor_trade_date": anchor_trade_date,
                                "window_return_pct": link_result.window_return_pct,
                                "window_volatility": link_result.window_volatility,
                                "abnormal_volume_ratio": link_result.abnormal_volume_ratio,
                                "correlation_score": link_result.correlation_score,
                                "confidence": link_result.confidence,
                                "link_status": link_result.link_status,
                            }
                        ).model_dump()
                    )
                else:
                    await upsert_analysis_event_link(
                        session,
                        event_id=raw_event.id,
                        ts_code=session_row.ts_code,
                        anchor_trade_date=None,
                        window_return_pct=None,
                        window_volatility=None,
                        abnormal_volume_ratio=None,
                        correlation_score=None,
                        confidence="low",
                        link_status="pending",
                    )
                    event_payloads.append(
                        AnalysisEventLinkResponse.model_validate(
                            {
                                "event_id": raw_event.id,
                                "scope": raw_event.scope,
                                "title": raw_event.title,
                                "published_at": raw_event.published_at,
                                "source": raw_event.source,
                                "macro_topic": raw_event.macro_topic,
                                "event_type": event_type,
                                "event_tags": event_tags,
                                "sentiment_label": sentiment.label,
                                "sentiment_score": sentiment.score,
                                "anchor_trade_date": None,
                                "window_return_pct": None,
                                "window_volatility": None,
                                "abnormal_volume_ratio": None,
                                "correlation_score": None,
                                "confidence": "low",
                                "link_status": "pending",
                            }
                        ).model_dump()
                    )

            await session.commit()
            factor_weights = calculate_factor_weights(event_payloads)

            async def on_delta(delta: str) -> None:
                session_row.summary_preview = f"{session_row.summary_preview or ''}{delta}"
                await session.commit()
                await event_bus.publish(
                    session_id,
                    "delta",
                    {
                        "session_id": session_id,
                        "delta": delta,
                        "content": session_row.summary_preview or "",
                    },
                )

            report_result = await generate_stock_analysis_report(
                ts_code=session_row.ts_code,
                instrument_name=instrument.name,
                events=event_payloads,
                factor_weights=factor_weights,
                session=session,
                use_web_search=session_row.use_web_search,
                on_delta=on_delta,
            )
            report = await create_analysis_report(
                session,
                ts_code=session_row.ts_code,
                status=report_result.status,
                summary=report_result.summary,
                risk_points=report_result.risk_points,
                factor_breakdown=report_result.factor_breakdown,
                topic=session_row.topic,
                published_from=None,
                published_to=None,
                generated_at=report_result.generated_at,
                trigger_source=session_row.trigger_source,
                anchor_event_id=session_row.anchor_event_id,
                anchor_event_title=next(
                    (
                        str(item.get("title"))
                        for item in event_payloads
                        if item.get("event_id") == session_row.anchor_event_id
                    ),
                    None,
                ),
                used_web_search=report_result.used_web_search,
                web_search_status=report_result.web_search_status,
                session_id=session_id,
                started_at=session_row.started_at,
                completed_at=report_result.generated_at,
                content_format="markdown",
                structured_sources=_build_structured_sources(event_payloads),
                web_sources=report_result.web_sources,
            )
            await session.flush()
            session_row.summary_preview = report_result.summary
            session_row.report_id = report.id
            session_row.status = "completed"
            session_row.completed_at = report_result.generated_at
            await session.commit()

            settings = get_settings()
            await cache_fresh_report_id(
                analysis_key,
                report.id,
                settings.analysis_report_freshness_minutes * 60,
            )
            await clear_cached_active_session_id(analysis_key, session_id)
            await event_bus.publish(
                session_id,
                "completed",
                {
                    "session_id": session_id,
                    "report_id": report.id,
                    "status": report_result.status,
                },
            )
        except Exception as exc:
            session_row = await load_analysis_session(session, session_id)
            if session_row is not None:
                session_row.status = "failed"
                session_row.error_message = str(exc)
                session_row.completed_at = datetime.now(UTC)
                await session.commit()
                await clear_cached_active_session_id(analysis_key, session_id)
            await event_bus.publish(
                session_id,
                "error",
                {
                    "session_id": session_id,
                    "detail": str(exc),
                },
            )
