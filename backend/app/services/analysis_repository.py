from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.analysis_agent_run import AnalysisAgentRun
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.services.news_latest_query_service import (
    build_latest_news_events_statement,
    build_news_event_identity_key,
)


def _normalize_event_tags(raw: str | None) -> list[str]:
    if not raw:
        return []

    return [item.strip() for item in raw.split(",") if item.strip()]


def build_trigger_source_group(trigger_source: str) -> str:
    return "watchlist" if trigger_source == "watchlist_daily" else "manual"


def build_analysis_key(
    *,
    ts_code: str,
    topic: str | None,
    anchor_event_id: str | None,
    use_web_search: bool,
    trigger_source: str,
    analysis_mode: str = "single",
) -> str:
    # 分析 key 用于会话去重，包含主题/锚点/检索开关等关键维度。
    return (
        f"{ts_code.strip().upper()}|{(topic or '').strip()}|{(anchor_event_id or '').strip()}|"
        f"{int(use_web_search)}|{build_trigger_source_group(trigger_source)}|{analysis_mode.strip() or 'single'}"
    )


async def load_stock_instrument(
    session: AsyncSession, ts_code: str
) -> StockInstrument | None:
    statement = select(StockInstrument).where(StockInstrument.ts_code == ts_code)
    return (await session.execute(statement)).scalar_one_or_none()


async def load_latest_snapshot(
    session: AsyncSession, ts_code: str
) -> StockDailySnapshot | None:
    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == ts_code)
        .order_by(StockDailySnapshot.trade_date.desc())
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def load_recent_news_events(
    session: AsyncSession,
    ts_code: str,
    *,
    topic: str | None,
    anchor_event_id: str | None,
    published_from: datetime | None,
    published_to: datetime | None,
    limit: int,
    candidate_limit: int | None = None,
) -> list[NewsEvent]:
    # 取数优先覆盖股票/政策/宏观三类，必要时按 topic 追加热点事件。
    resolved_limit = max(limit, candidate_limit or limit)
    scope_conditions = [
        and_(NewsEvent.scope == "stock", NewsEvent.ts_code == ts_code),
        NewsEvent.scope == "policy",
    ]
    if topic:
        scope_conditions.append(
            and_(NewsEvent.scope == "hot", NewsEvent.macro_topic == topic)
        )
    else:
        # 默认分析必须混入热点上下文，避免只剩个股与政策事件。
        scope_conditions.append(NewsEvent.scope == "hot")

    base_statement = select(NewsEvent).where(or_(*scope_conditions))
    if topic:
        base_statement = base_statement.where(
            or_(NewsEvent.scope.in_(("stock", "policy")), NewsEvent.macro_topic == topic)
        )
    if published_from is not None:
        base_statement = base_statement.where(NewsEvent.published_at >= published_from)
    if published_to is not None:
        base_statement = base_statement.where(NewsEvent.published_at <= published_to)

    latest_statement = build_latest_news_events_statement(
        base_statement=base_statement,
        apply_default_order=True,
    )
    if not anchor_event_id:
        latest_statement = latest_statement.limit(resolved_limit)
        return (await session.execute(latest_statement)).scalars().all()

    rows = (
        await session.execute(latest_statement.limit(resolved_limit))
    ).scalars().all()

    anchor_row = await session.get(NewsEvent, anchor_event_id)
    if anchor_row is None:
        # 锚点不存在时直接回退到最新列表，避免空锚点导致全量丢失。
        return rows[:limit]

    ordered_rows: list[NewsEvent] = [anchor_row]
    seen_keys = {build_news_event_identity_key(anchor_row)}
    if anchor_row.cluster_key:
        # 同一聚类的兄弟事件需要优先串联，保证摘要上下文一致。
        sibling_base_statement = select(NewsEvent).where(
            NewsEvent.cluster_key == anchor_row.cluster_key
        )
        sibling_statement = build_latest_news_events_statement(
            base_statement=sibling_base_statement,
            apply_default_order=True,
        )
        sibling_rows = (await session.execute(sibling_statement)).scalars().all()
        for sibling in sibling_rows:
            sibling_key = build_news_event_identity_key(sibling)
            if sibling_key in seen_keys:
                continue
            ordered_rows.append(sibling)
            seen_keys.add(sibling_key)

    for row in rows:
        row_key = build_news_event_identity_key(row)
        if row_key in seen_keys:
            continue
        ordered_rows.append(row)
        seen_keys.add(row_key)

    return ordered_rows[:resolved_limit]


async def load_price_window_rows(
    session: AsyncSession,
    ts_code: str,
    *,
    anchor_from: date | None,
    window_size: int = 5,
) -> list[dict[str, object]]:
    if anchor_from is None:
        return []

    # 价格窗口以“锚点日期起始”的前向窗口为准，供事件关联度计算使用。
    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == ts_code)
        .where(StockDailySnapshot.trade_date >= anchor_from)
        .order_by(StockDailySnapshot.trade_date.asc())
        .limit(window_size)
    )
    rows = (await session.execute(statement)).scalars().all()
    return [
        {
            "trade_date": row.trade_date,
            "close": float(row.close) if row.close is not None else None,
            "vol": float(row.vol) if row.vol is not None else None,
        }
        for row in rows
    ]


async def upsert_analysis_event_link(
    session: AsyncSession,
    *,
    event_id: str,
    ts_code: str,
    anchor_trade_date: date | None,
    window_return_pct: float | None,
    window_volatility: float | None,
    abnormal_volume_ratio: float | None,
    correlation_score: float | None,
    confidence: str | None,
    link_status: str | None,
) -> AnalysisEventLink:
    row = await session.get(AnalysisEventLink, (event_id, ts_code))
    if row is None:
        row = AnalysisEventLink(event_id=event_id, ts_code=ts_code)
        session.add(row)

    # 关联指标以最新结果覆盖，确保分析重复运行时口径一致。
    row.anchor_trade_date = anchor_trade_date
    row.window_return_pct = window_return_pct
    row.window_volatility = window_volatility
    row.abnormal_volume_ratio = abnormal_volume_ratio
    row.correlation_score = correlation_score
    row.confidence = confidence
    row.link_status = link_status
    return row


async def create_analysis_report(
    session: AsyncSession,
    *,
    ts_code: str,
    status: str,
    summary: str,
    risk_points: list[str],
    factor_breakdown: list[dict[str, object]],
    topic: str | None,
    published_from: datetime | None,
    published_to: datetime | None,
    generated_at: datetime,
    trigger_source: str,
    anchor_event_id: str | None,
    anchor_event_title: str | None,
    used_web_search: bool,
    web_search_status: str,
    session_id: str | None,
    started_at: datetime | None,
    completed_at: datetime | None,
    content_format: str,
    analysis_mode: str = "single",
    orchestrator_version: str | None = None,
    selected_hypothesis: str | None = None,
    decision_confidence: str | None = None,
    decision_reason_summary: str | None = None,
    structured_sources: list[dict[str, object]] | None = None,
    evidence_event_count: int | None = None,
    evidence_events: list[dict[str, object]] | None = None,
    web_sources: list[dict[str, object]] | None = None,
    prompt_version: str | None = None,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    token_usage_input: int | None = None,
    token_usage_output: int | None = None,
    cost_estimate: float | None = None,
    failure_type: str | None = None,
) -> AnalysisReport:
    report = AnalysisReport(
        ts_code=ts_code,
        status=status,
        summary=summary,
        risk_points=risk_points,
        factor_breakdown=factor_breakdown,
        topic=topic,
        published_from=published_from,
        published_to=published_to,
        generated_at=generated_at,
        trigger_source=trigger_source,
        anchor_event_id=anchor_event_id,
        anchor_event_title=anchor_event_title,
        used_web_search=used_web_search,
        web_search_status=web_search_status,
        session_id=session_id,
        started_at=started_at,
        completed_at=completed_at,
        content_format=content_format,
        analysis_mode=analysis_mode,
        orchestrator_version=orchestrator_version,
        selected_hypothesis=selected_hypothesis,
        decision_confidence=decision_confidence,
        decision_reason_summary=decision_reason_summary,
        structured_sources=structured_sources,
        evidence_event_count=evidence_event_count,
        evidence_events=evidence_events,
        web_sources=web_sources,
        prompt_version=prompt_version,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        token_usage_input=token_usage_input,
        token_usage_output=token_usage_output,
        cost_estimate=cost_estimate,
        failure_type=failure_type,
    )
    session.add(report)
    return report


async def load_analysis_events(
    session: AsyncSession,
    ts_code: str,
    limit: int = 20,
    anchor_event_id: str | None = None,
    candidate_limit: int | None = None,
) -> list[dict[str, object | None]]:
    resolved_limit = max(limit, candidate_limit or limit)
    news_alias = aliased(NewsEvent)
    statement = (
        select(AnalysisEventLink, news_alias)
        .join(news_alias, AnalysisEventLink.event_id == news_alias.id)
        .where(AnalysisEventLink.ts_code == ts_code)
        .order_by(AnalysisEventLink.created_at.desc())
        .limit(resolved_limit)
    )
    rows = (await session.execute(statement)).all()
    events: list[dict[str, object | None]] = []
    for link, news in rows:
        events.append(
            {
                "event_id": link.event_id,
                "scope": news.scope,
                "title": news.title,
                "published_at": news.published_at,
                "source": news.source,
                "macro_topic": news.macro_topic,
                "event_type": news.event_type,
                "event_tags": _normalize_event_tags(news.event_tags),
                "sentiment_label": news.sentiment_label,
                "sentiment_score": news.sentiment_score,
                "anchor_trade_date": link.anchor_trade_date,
                "window_return_pct": link.window_return_pct,
                "window_volatility": link.window_volatility,
                "abnormal_volume_ratio": link.abnormal_volume_ratio,
                "correlation_score": link.correlation_score,
                "confidence": link.confidence,
                "link_status": link.link_status,
                "cluster_key": news.cluster_key,
                "ts_code": news.ts_code,
                "url": news.url,
                "fetched_at": news.fetched_at,
                "news_created_at": news.created_at,
                "source_priority": news.source_priority,
                "link_created_at": link.created_at,
            }
        )

    if anchor_event_id:
        events.sort(key=lambda item: 0 if item["event_id"] == anchor_event_id else 1)

    return events


async def load_latest_report(
    session: AsyncSession,
    ts_code: str,
    *,
    topic: str | None = None,
    anchor_event_id: str | None = None,
    analysis_mode: str = "single",
) -> AnalysisReport | None:
    statement = select(AnalysisReport).where(AnalysisReport.ts_code == ts_code).where(
        AnalysisReport.analysis_mode == analysis_mode
    )
    if topic:
        statement = statement.where(AnalysisReport.topic == topic)
    if anchor_event_id is None:
        statement = statement.where(AnalysisReport.anchor_event_id.is_(None))
    else:
        statement = statement.where(AnalysisReport.anchor_event_id == anchor_event_id)
    statement = statement.order_by(AnalysisReport.generated_at.desc()).limit(1)
    return (await session.execute(statement)).scalar_one_or_none()


async def load_analysis_report_by_id(
    session: AsyncSession,
    report_id: str,
) -> AnalysisReport | None:
    return await session.get(AnalysisReport, report_id)


async def load_latest_fresh_report(
    session: AsyncSession,
    *,
    ts_code: str,
    topic: str | None,
    anchor_event_id: str | None,
    freshness_minutes: int,
    analysis_mode: str = "single",
) -> AnalysisReport | None:
    freshness_threshold = datetime.now(UTC) - timedelta(minutes=freshness_minutes)
    statement = (
        select(AnalysisReport)
        .where(AnalysisReport.ts_code == ts_code)
        .where(AnalysisReport.generated_at >= freshness_threshold)
        .where(AnalysisReport.analysis_mode == analysis_mode)
    )
    if topic is None:
        statement = statement.where(AnalysisReport.topic.is_(None))
    else:
        statement = statement.where(AnalysisReport.topic == topic)
    if anchor_event_id is None:
        statement = statement.where(AnalysisReport.anchor_event_id.is_(None))
    else:
        statement = statement.where(AnalysisReport.anchor_event_id == anchor_event_id)
    statement = statement.order_by(AnalysisReport.generated_at.desc()).limit(1)
    return (await session.execute(statement)).scalar_one_or_none()


async def list_analysis_reports(
    session: AsyncSession,
    *,
    ts_code: str,
    topic: str | None = None,
    anchor_event_id: str | None = None,
    limit: int,
    analysis_mode: str = "single",
) -> list[AnalysisReport]:
    statement = select(AnalysisReport).where(AnalysisReport.ts_code == ts_code).where(
        AnalysisReport.analysis_mode == analysis_mode
    )
    if topic:
        statement = statement.where(AnalysisReport.topic == topic)
    if anchor_event_id is None:
        statement = statement.where(AnalysisReport.anchor_event_id.is_(None))
    else:
        statement = statement.where(AnalysisReport.anchor_event_id == anchor_event_id)
    statement = statement.order_by(AnalysisReport.generated_at.desc()).limit(limit)
    return (await session.execute(statement)).scalars().all()


async def update_analysis_report_web_sources(
    session: AsyncSession,
    *,
    report: AnalysisReport,
    web_sources: list[dict[str, object]] | None,
) -> AnalysisReport:
    report.web_sources = web_sources
    await session.flush()
    return report


async def create_analysis_session_record(
    session: AsyncSession,
    *,
    analysis_key: str,
    ts_code: str,
    topic: str | None,
    anchor_event_id: str | None,
    use_web_search: bool,
    trigger_source: str,
    analysis_mode: str = "single",
    system_job_id: str | None = None,
    prompt_version: str | None = None,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    orchestrator_version: str | None = None,
) -> AnalysisGenerationSession:
    row = AnalysisGenerationSession(
        analysis_key=analysis_key,
        ts_code=ts_code,
        topic=topic,
        anchor_event_id=anchor_event_id,
        use_web_search=use_web_search,
        analysis_mode=analysis_mode,
        orchestrator_version=orchestrator_version,
        trigger_source=trigger_source,
        trigger_source_group=build_trigger_source_group(trigger_source),
        status="queued",
        current_stage="queued",
        stage_message="等待分析任务执行",
        progress_current=0,
        progress_total=0,
        role_count=0,
        role_completed_count=0,
        active_role_key=None,
        system_job_id=system_job_id,
        prompt_version=prompt_version,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
    )
    session.add(row)
    return row


async def load_active_session_by_key(
    session: AsyncSession,
    *,
    analysis_key: str,
    active_after: datetime,
) -> AnalysisGenerationSession | None:
    statement = (
        select(AnalysisGenerationSession)
        .where(AnalysisGenerationSession.analysis_key == analysis_key)
        .where(AnalysisGenerationSession.status.in_(("queued", "running")))
        .where(AnalysisGenerationSession.updated_at >= active_after)
        .order_by(AnalysisGenerationSession.updated_at.desc())
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def load_analysis_session(
    session: AsyncSession, session_id: str
) -> AnalysisGenerationSession | None:
    return await session.get(AnalysisGenerationSession, session_id)


async def claim_next_analysis_session_for_worker(
    session: AsyncSession,
    *,
    stale_before: datetime,
) -> str | None:
    now = datetime.now(UTC)

    def _build_claim_statement(
        *,
        status: str,
        order_by,
        updated_before: datetime | None = None,
    ):
        candidate_statement = (
            select(AnalysisGenerationSession.id)
            .where(AnalysisGenerationSession.status == status)
            .order_by(*order_by)
            .limit(1)
        )
        if updated_before is not None:
            candidate_statement = candidate_statement.where(
                AnalysisGenerationSession.updated_at < updated_before
            )

        get_bind = getattr(session, "get_bind", None)
        if callable(get_bind):
            bind = get_bind()
            dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
            if dialect_name == "postgresql":
                # PostgreSQL 下显式跳过已锁定候选，避免多个 worker 互相阻塞或重复领取。
                candidate_statement = candidate_statement.with_for_update(
                    skip_locked=True
                )

        candidate_id = candidate_statement.scalar_subquery()
        return (
            update(AnalysisGenerationSession)
            .where(AnalysisGenerationSession.id == candidate_id)
            .values(
                status="running",
                started_at=now,
                completed_at=None,
                error_message=None,
                failure_type=None,
            )
            .returning(AnalysisGenerationSession.id)
        )

    # 关键流程：Worker 先原子领取 queued，只有没有 queued 时才回收 stale running，避免饿死新任务。
    queued_result = await session.execute(
        _build_claim_statement(
            status="queued",
            order_by=(
                AnalysisGenerationSession.created_at.asc(),
                AnalysisGenerationSession.id.asc(),
            ),
        )
    )
    queued_id = queued_result.scalar_one_or_none()
    if queued_id is not None:
        return queued_id

    stale_result = await session.execute(
        _build_claim_statement(
            status="running",
            updated_before=stale_before,
            order_by=(
                AnalysisGenerationSession.updated_at.asc(),
                AnalysisGenerationSession.id.asc(),
            ),
        )
    )
    return stale_result.scalar_one_or_none()


async def create_analysis_agent_run(
    session: AsyncSession,
    *,
    session_id: str,
    report_id: str | None,
    role_key: str,
    role_label: str,
    status: str,
    sort_order: int,
    summary: str | None,
    input_snapshot: dict[str, object] | None,
    output_payload: dict[str, object] | None,
    used_web_search: bool,
    web_search_status: str,
    web_sources: list[dict[str, object]] | None,
    prompt_version: str | None,
    model_name: str | None,
    reasoning_effort: str | None,
    token_usage_input: int | None,
    token_usage_output: int | None,
    cost_estimate: float | None,
    failure_type: str | None,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> AnalysisAgentRun:
    row = AnalysisAgentRun(
        session_id=session_id,
        report_id=report_id,
        role_key=role_key,
        role_label=role_label,
        status=status,
        sort_order=sort_order,
        summary=summary,
        input_snapshot=input_snapshot,
        output_payload=output_payload,
        used_web_search=used_web_search,
        web_search_status=web_search_status,
        web_sources=web_sources,
        prompt_version=prompt_version,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        token_usage_input=token_usage_input,
        token_usage_output=token_usage_output,
        cost_estimate=cost_estimate,
        failure_type=failure_type,
        started_at=started_at,
        completed_at=completed_at,
    )
    session.add(row)
    return row


async def list_analysis_agent_runs_for_report(
    session: AsyncSession,
    report_id: str,
) -> list[AnalysisAgentRun]:
    statement = (
        select(AnalysisAgentRun)
        .where(AnalysisAgentRun.report_id == report_id)
        .order_by(AnalysisAgentRun.sort_order.asc(), AnalysisAgentRun.created_at.asc())
    )
    return (await session.execute(statement)).scalars().all()


async def list_analysis_agent_runs_for_session(
    session: AsyncSession,
    session_id: str,
) -> list[AnalysisAgentRun]:
    statement = (
        select(AnalysisAgentRun)
        .where(AnalysisAgentRun.session_id == session_id)
        .order_by(AnalysisAgentRun.sort_order.asc(), AnalysisAgentRun.created_at.asc())
    )
    return (await session.execute(statement)).scalars().all()

