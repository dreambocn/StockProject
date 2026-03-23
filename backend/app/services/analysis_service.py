from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.analysis import (
    AnalysisEventLinkResponse,
    AnalysisReportResponse,
    StockAnalysisSummaryResponse,
)
from app.schemas.stocks import (
    StockDailySnapshotResponse,
    StockInstrumentResponse,
)
from app.services.analysis_repository import (
    create_analysis_report,
    load_analysis_events,
    load_latest_report,
    load_latest_snapshot,
    load_price_window_rows,
    load_recent_news_events,
    load_stock_instrument,
    upsert_analysis_event_link,
)
from app.services.event_link_service import build_event_link_result
from app.services.factor_weight_service import calculate_factor_weights
from app.services.key_event_extraction_service import extract_key_event_types
from app.services.llm_analysis_service import generate_stock_analysis_report
from app.services.news_sentiment_service import analyze_news_sentiment


def _derive_status(has_report: bool, event_count: int) -> Literal["ready", "partial", "pending"]:
    if has_report:
        return "ready"
    if event_count > 0:
        return "partial"
    return "pending"


def _resolve_event_type(*, scope: str, source: str, event_tags: list[str]) -> str:
    if scope == "policy" or "policy" in event_tags or "regulation" in event_tags:
        return "policy"
    if source == "cninfo_announcement" or "announcement" in event_tags:
        return "announcement"
    return "news"


def _build_report_payload(report_obj: object | None) -> dict[str, object] | None:
    if report_obj is None:
        return None

    report = AnalysisReportResponse.model_validate(
        {
            "status": getattr(report_obj, "status", "pending") or "pending",
            "summary": getattr(report_obj, "summary", ""),
            "risk_points": getattr(report_obj, "risk_points", None) or [],
            "factor_breakdown": getattr(report_obj, "factor_breakdown", None) or [],
            "generated_at": getattr(report_obj, "generated_at", None),
            "topic": getattr(report_obj, "topic", None),
            "published_from": getattr(report_obj, "published_from", None),
            "published_to": getattr(report_obj, "published_to", None),
        }
    )
    return report.model_dump()


async def get_stock_analysis_summary(
    session: AsyncSession,
    ts_code: str,
    *,
    topic: str | None = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    event_limit: int = 20,
) -> dict[str, object | None]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await load_stock_instrument(session, normalized_ts_code)
    snapshot = await load_latest_snapshot(session, normalized_ts_code)
    raw_events = []
    if instrument is not None:
        raw_events = await load_recent_news_events(
            session,
            normalized_ts_code,
            topic=topic,
            published_from=published_from,
            published_to=published_to,
            limit=event_limit,
        )

    instrument_obj = (
        StockInstrumentResponse.model_validate(instrument) if instrument else None
    )
    snapshot_obj = (
        StockDailySnapshotResponse.model_validate(snapshot) if snapshot else None
    )
    instrument_payload = instrument_obj.model_dump() if instrument_obj else None
    snapshot_payload = snapshot_obj.model_dump() if snapshot_obj else None

    event_payloads: list[dict[str, object | None]] = []
    report_payload: dict[str, object] | None = None
    generated_at = None
    resolved_topic = topic
    resolved_published_from = published_from
    resolved_published_to = published_to

    if raw_events:
        # 关键流程：分析接口只消费数据库中的事件与行情快照，不在读取阶段回源外部接口。
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
                normalized_ts_code,
                anchor_from=raw_event.published_at.date() if raw_event.published_at else None,
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
                    ts_code=normalized_ts_code,
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
                    ts_code=normalized_ts_code,
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

        factor_weights = calculate_factor_weights(event_payloads)
        report_result = await generate_stock_analysis_report(
            ts_code=normalized_ts_code,
            instrument_name=instrument_obj.name if instrument_obj else None,
            events=event_payloads,
            factor_weights=factor_weights,
        )
        await create_analysis_report(
            session,
            ts_code=normalized_ts_code,
            status=report_result.status,
            summary=report_result.summary,
            risk_points=report_result.risk_points,
            factor_breakdown=report_result.factor_breakdown,
            topic=topic,
            published_from=published_from,
            published_to=published_to,
            generated_at=report_result.generated_at,
        )
        await session.commit()
        report_payload = _build_report_payload(report_result)
        generated_at = report_result.generated_at
    else:
        persisted_events = await load_analysis_events(
            session,
            normalized_ts_code,
            limit=event_limit,
        )
        persisted_report = await load_latest_report(session, normalized_ts_code)
        validated_events = [
            AnalysisEventLinkResponse.model_validate(item) for item in persisted_events
        ]
        event_payloads = [event.model_dump() for event in validated_events]
        report_payload = _build_report_payload(persisted_report)
        generated_at = (
            getattr(persisted_report, "generated_at", None) if persisted_report else None
        )
        if persisted_report is not None:
            resolved_topic = persisted_report.topic
            resolved_published_from = persisted_report.published_from
            resolved_published_to = persisted_report.published_to

    status = _derive_status(report_payload is not None, len(event_payloads))

    result = {
        "ts_code": normalized_ts_code,
        "instrument": instrument_payload,
        "latest_snapshot": snapshot_payload,
        "status": status,
        "generated_at": generated_at,
        "topic": resolved_topic,
        "published_from": resolved_published_from,
        "published_to": resolved_published_to,
        "event_count": len(event_payloads),
        "events": event_payloads,
        "report": report_payload,
    }

    StockAnalysisSummaryResponse.model_validate(result)
    return result
