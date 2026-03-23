from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument


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
    use_web_search: bool,
    trigger_source: str,
) -> str:
    return (
        f"{ts_code.strip().upper()}|{(topic or '').strip()}|"
        f"{int(use_web_search)}|{build_trigger_source_group(trigger_source)}"
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
    published_from: datetime | None,
    published_to: datetime | None,
    limit: int,
) -> list[NewsEvent]:
    scope_conditions = [
        and_(NewsEvent.scope == "stock", NewsEvent.ts_code == ts_code),
        NewsEvent.scope == "policy",
    ]
    if topic:
        scope_conditions.append(
            and_(NewsEvent.scope == "hot", NewsEvent.macro_topic == topic)
        )

    statement = select(NewsEvent).where(or_(*scope_conditions))
    if topic:
        statement = statement.where(
            or_(NewsEvent.scope.in_(("stock", "policy")), NewsEvent.macro_topic == topic)
        )
    if published_from is not None:
        statement = statement.where(NewsEvent.published_at >= published_from)
    if published_to is not None:
        statement = statement.where(NewsEvent.published_at <= published_to)

    statement = statement.order_by(
        NewsEvent.published_at.desc(), NewsEvent.created_at.desc()
    ).limit(limit)
    return (await session.execute(statement)).scalars().all()


async def load_price_window_rows(
    session: AsyncSession,
    ts_code: str,
    *,
    anchor_from: date | None,
    window_size: int = 5,
) -> list[dict[str, object]]:
    if anchor_from is None:
        return []

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
    used_web_search: bool,
    web_search_status: str,
    session_id: str | None,
    started_at: datetime | None,
    completed_at: datetime | None,
    content_format: str,
    web_sources: list[dict[str, object]] | None,
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
        used_web_search=used_web_search,
        web_search_status=web_search_status,
        session_id=session_id,
        started_at=started_at,
        completed_at=completed_at,
        content_format=content_format,
        web_sources=web_sources,
    )
    session.add(report)
    return report


async def load_analysis_events(
    session: AsyncSession, ts_code: str, limit: int = 20
) -> list[dict[str, object | None]]:
    news_alias = aliased(NewsEvent)
    statement = (
        select(AnalysisEventLink, news_alias)
        .join(news_alias, AnalysisEventLink.event_id == news_alias.id)
        .where(AnalysisEventLink.ts_code == ts_code)
        .order_by(AnalysisEventLink.created_at.desc())
        .limit(limit)
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
            }
        )

    return events


async def load_latest_report(
    session: AsyncSession,
    ts_code: str,
    *,
    topic: str | None = None,
) -> AnalysisReport | None:
    statement = select(AnalysisReport).where(AnalysisReport.ts_code == ts_code)
    if topic:
        statement = statement.where(AnalysisReport.topic == topic)
    statement = statement.order_by(AnalysisReport.generated_at.desc()).limit(1)
    return (await session.execute(statement)).scalar_one_or_none()


async def load_latest_fresh_report(
    session: AsyncSession,
    *,
    ts_code: str,
    topic: str | None,
    use_web_search: bool,
    trigger_source: str,
    freshness_minutes: int,
) -> AnalysisReport | None:
    freshness_threshold = datetime.now(UTC) - timedelta(minutes=freshness_minutes)
    statement = (
        select(AnalysisReport)
        .where(AnalysisReport.ts_code == ts_code)
        .where(AnalysisReport.used_web_search == use_web_search)
        .where(AnalysisReport.trigger_source == trigger_source)
        .where(AnalysisReport.generated_at >= freshness_threshold)
    )
    if topic is None:
        statement = statement.where(AnalysisReport.topic.is_(None))
    else:
        statement = statement.where(AnalysisReport.topic == topic)
    statement = statement.order_by(AnalysisReport.generated_at.desc()).limit(1)
    return (await session.execute(statement)).scalar_one_or_none()


async def list_analysis_reports(
    session: AsyncSession,
    *,
    ts_code: str,
    limit: int,
) -> list[AnalysisReport]:
    statement = (
        select(AnalysisReport)
        .where(AnalysisReport.ts_code == ts_code)
        .order_by(AnalysisReport.generated_at.desc())
        .limit(limit)
    )
    return (await session.execute(statement)).scalars().all()


async def create_analysis_session_record(
    session: AsyncSession,
    *,
    analysis_key: str,
    ts_code: str,
    topic: str | None,
    use_web_search: bool,
    trigger_source: str,
) -> AnalysisGenerationSession:
    row = AnalysisGenerationSession(
        analysis_key=analysis_key,
        ts_code=ts_code,
        topic=topic,
        use_web_search=use_web_search,
        trigger_source=trigger_source,
        trigger_source_group=build_trigger_source_group(trigger_source),
        status="queued",
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

