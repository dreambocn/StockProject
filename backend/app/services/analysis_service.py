from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.analysis import AnalysisReportResponse, StockAnalysisSummaryResponse
from app.schemas.stocks import StockDailySnapshotResponse, StockInstrumentResponse
from app.services.analysis_repository import (
    load_analysis_events,
    load_latest_report,
    load_latest_snapshot,
    load_stock_instrument,
)


def _derive_status(has_report: bool, event_count: int) -> Literal["ready", "partial", "pending"]:
    if has_report:
        return "ready"
    if event_count > 0:
        return "partial"
    return "pending"


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
    persisted_events = await load_analysis_events(
        session,
        normalized_ts_code,
        limit=event_limit,
    )
    persisted_report = await load_latest_report(session, normalized_ts_code)

    instrument_obj = (
        StockInstrumentResponse.model_validate(instrument) if instrument else None
    )
    snapshot_obj = (
        StockDailySnapshotResponse.model_validate(snapshot) if snapshot else None
    )
    instrument_payload = instrument_obj.model_dump() if instrument_obj else None
    snapshot_payload = snapshot_obj.model_dump() if snapshot_obj else None
    report_payload = _build_report_payload(persisted_report)

    # 关键流程：基础阶段坚持 DB-first，只聚合已落库的分析结果，避免接口读取时触发额外计算。
    result = {
        "ts_code": normalized_ts_code,
        "instrument": instrument_payload,
        "latest_snapshot": snapshot_payload,
        "status": _derive_status(report_payload is not None, len(persisted_events)),
        "generated_at": getattr(persisted_report, "generated_at", None)
        if persisted_report
        else None,
        "topic": getattr(persisted_report, "topic", None) if persisted_report else topic,
        "published_from": getattr(persisted_report, "published_from", None)
        if persisted_report
        else published_from,
        "published_to": getattr(persisted_report, "published_to", None)
        if persisted_report
        else published_to,
        "event_count": len(persisted_events),
        "events": persisted_events,
        "report": report_payload,
    }

    StockAnalysisSummaryResponse.model_validate(result)
    return result
