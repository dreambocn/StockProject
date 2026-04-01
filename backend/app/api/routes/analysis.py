from datetime import UTC, datetime
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.analysis import (
    AnalysisReportArchiveListResponse,
    AnalysisReportEvidenceResponse,
    AnalysisSessionCreateRequest,
    AnalysisSessionCreateResponse,
    AnalysisSessionStatusResponse,
    StockAnalysisSummaryResponse,
)
from app.services.analysis_repository import load_analysis_session
from app.services.analysis_runtime_service import event_bus
from app.services.analysis_service import (
    AnalysisNotFoundError,
    AnalysisReportNotFoundError,
    get_analysis_report_evidence,
    get_stock_analysis_summary,
    list_stock_analysis_report_archives,
    start_analysis_session,
)
from app.services.analysis_export_service import (
    AnalysisExportNotFoundError,
    load_analysis_report_for_export,
    render_report_html,
    render_report_markdown,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/stocks/{ts_code}/summary", response_model=StockAnalysisSummaryResponse)
async def get_stock_analysis_summary_route(
    ts_code: str,
    topic: str | None = Query(default=None),
    event_id: str | None = Query(default=None),
    published_from: datetime | None = Query(default=None),
    published_to: datetime | None = Query(default=None),
    event_limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> StockAnalysisSummaryResponse:
    # 摘要查询仅做参数透传与校验，核心业务边界在服务层统一处理。
    payload = await get_stock_analysis_summary(
        session,
        ts_code,
        topic=topic,
        event_id=event_id,
        published_from=published_from,
        published_to=published_to,
        event_limit=event_limit,
    )
    return StockAnalysisSummaryResponse.model_validate(payload)


@router.post(
    "/stocks/{ts_code}/sessions",
    response_model=AnalysisSessionCreateResponse,
)
async def create_analysis_session_route(
    ts_code: str,
    request: AnalysisSessionCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisSessionCreateResponse:
    try:
        payload = await start_analysis_session(
            session,
            ts_code,
            topic=request.topic,
            event_id=request.event_id,
            force_refresh=request.force_refresh,
            use_web_search=request.use_web_search,
            trigger_source=request.trigger_source,
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AnalysisSessionCreateResponse.model_validate(payload)


@router.get(
    "/sessions/{session_id}",
    response_model=AnalysisSessionStatusResponse,
)
async def get_analysis_session_status_route(
    session_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisSessionStatusResponse:
    session_row = await load_analysis_session(session, session_id)
    if session_row is None:
        raise HTTPException(status_code=404, detail="analysis session not found")

    return AnalysisSessionStatusResponse.model_validate(
        {
            "session_id": session_row.id,
            "status": session_row.status,
            "current_stage": session_row.current_stage,
            "stage_message": session_row.stage_message,
            "summary_preview": session_row.summary_preview,
            "progress_current": session_row.progress_current,
            "progress_total": session_row.progress_total,
            "report_id": session_row.report_id,
            "error_message": session_row.error_message,
            "started_at": _normalize_utc_datetime(session_row.started_at),
            "completed_at": _normalize_utc_datetime(session_row.completed_at),
            "heartbeat_at": _normalize_utc_datetime(session_row.heartbeat_at),
        }
    )


@router.get(
    "/stocks/{ts_code}/reports",
    response_model=AnalysisReportArchiveListResponse,
)
async def get_stock_analysis_reports_route(
    ts_code: str,
    topic: str | None = Query(default=None),
    event_id: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisReportArchiveListResponse:
    payload = await list_stock_analysis_report_archives(
        session,
        ts_code,
        topic=topic,
        event_id=event_id,
        limit=limit,
    )
    return AnalysisReportArchiveListResponse.model_validate(payload)


@router.get("/reports/{report_id}/export")
async def export_analysis_report_route(
    report_id: str,
    format: str = Query(default="markdown"),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    normalized_format = format.strip().lower() or "markdown"
    if normalized_format not in {"markdown", "html"}:
        raise HTTPException(status_code=422, detail="invalid export format")

    try:
        report = await load_analysis_report_for_export(session, report_id=report_id)
    except AnalysisExportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if normalized_format == "html":
        html_content = render_report_html(report)
        return Response(
            content=html_content,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{report.ts_code}-{report.id}.html"'
                )
            },
        )

    markdown_content = render_report_markdown(report)
    return Response(
        content=markdown_content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{report.ts_code}-{report.id}.md"'
            )
        },
    )


@router.get(
    "/reports/{report_id}/evidence",
    response_model=AnalysisReportEvidenceResponse,
)
async def get_analysis_report_evidence_route(
    report_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisReportEvidenceResponse:
    try:
        payload = await get_analysis_report_evidence(session, report_id)
    except AnalysisReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AnalysisReportEvidenceResponse.model_validate(payload)


def _to_sse_payload(event: str, payload: dict[str, object]) -> str:
    # SSE 必须是纯文本协议格式，避免二次 JSON 包裹导致前端解析异常。
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {serialized}\n\n"


@router.get("/sessions/{session_id}/events")
async def stream_analysis_session_events_route(
    session_id: str,
    reused: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    session_row = await load_analysis_session(session, session_id)
    if session_row is None:
        raise HTTPException(status_code=404, detail="analysis session not found")

    async def event_stream():
        # 连接建立后先推送现有状态，确保前端有“可用的初始态”。
        yield _to_sse_payload(
            "status",
            {"session_id": session_id, "status": session_row.status},
        )
        if reused:
            # reused 表示复用历史会话，前端可以跳过“生成中”动画。
            yield _to_sse_payload(
                "reused",
                {"session_id": session_id, "status": session_row.status},
            )
        if session_row.summary_preview:
            # 预览文本是历史残留片段，先推送以便快速回显。
            yield _to_sse_payload(
                "delta",
                {
                    "session_id": session_id,
                    "delta": session_row.summary_preview,
                    "content": session_row.summary_preview,
                },
            )
        if session_row.status == "completed":
            # 已完成会话直接下发 completed，避免进入订阅循环。
            yield _to_sse_payload(
                "completed",
                {
                    "session_id": session_id,
                    "report_id": session_row.report_id,
                    "status": "completed",
                },
            )
            return
        if session_row.status == "failed":
            # 失败态立即返回 error，前端无需再等消息流。
            yield _to_sse_payload(
                "error",
                {
                    "session_id": session_id,
                    "detail": session_row.error_message or "analysis session failed",
                },
            )
            return

        async with event_bus.subscribe(session_id) as queue:
            while True:
                event_name, payload = await queue.get()
                yield _to_sse_payload(event_name, payload)
                if event_name in {"completed", "error"}:
                    # 终态事件到达后主动结束流，释放连接资源。
                    return

    return StreamingResponse(event_stream(), media_type="text/event-stream")
