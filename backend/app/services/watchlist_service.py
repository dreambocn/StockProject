from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_watchlist_item import UserWatchlistItem
from app.schemas.watchlist import (
    WatchlistFeedResponse,
    WatchlistItemCreateRequest,
    WatchlistItemResponse,
    WatchlistItemUpdateRequest,
    WatchlistResponse,
)
from app.services.analysis_repository import load_latest_report, load_stock_instrument
from app.services.analysis_service import serialize_report_archive_item


class WatchlistConflictError(Exception):
    pass


class WatchlistNotFoundError(Exception):
    pass


async def _load_watchlist_item(
    session: AsyncSession,
    *,
    user_id: str,
    ts_code: str,
) -> UserWatchlistItem | None:
    statement = (
        select(UserWatchlistItem)
        .where(UserWatchlistItem.user_id == user_id)
        .where(UserWatchlistItem.ts_code == ts_code)
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def _serialize_watchlist_item(
    session: AsyncSession, item: UserWatchlistItem
) -> dict[str, object]:
    instrument = await load_stock_instrument(session, item.ts_code)
    latest_report = await load_latest_report(session, item.ts_code)
    return WatchlistItemResponse.model_validate(
        {
            "id": item.id,
            "ts_code": item.ts_code,
            "hourly_sync_enabled": item.hourly_sync_enabled,
            "daily_analysis_enabled": item.daily_analysis_enabled,
            "web_search_enabled": item.web_search_enabled,
            "last_hourly_sync_at": item.last_hourly_sync_at,
            "last_daily_analysis_at": item.last_daily_analysis_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "instrument": instrument,
            "latest_report": (
                serialize_report_archive_item(latest_report)
                if latest_report is not None
                else None
            ),
        }
    ).model_dump()


async def list_watchlist(
    session: AsyncSession, *, user_id: str
) -> dict[str, object]:
    statement = (
        select(UserWatchlistItem)
        .where(UserWatchlistItem.user_id == user_id)
        .order_by(UserWatchlistItem.created_at.desc())
    )
    items = (await session.execute(statement)).scalars().all()
    payload = [await _serialize_watchlist_item(session, item) for item in items]
    return WatchlistResponse(items=payload).model_dump()


async def create_watchlist_item(
    session: AsyncSession,
    *,
    user_id: str,
    payload: WatchlistItemCreateRequest,
) -> dict[str, object]:
    normalized_ts_code = payload.ts_code.strip().upper()
    instrument = await load_stock_instrument(session, normalized_ts_code)
    if instrument is None:
        raise WatchlistNotFoundError("stock not found")

    existed = await _load_watchlist_item(
        session,
        user_id=user_id,
        ts_code=normalized_ts_code,
    )
    if existed is not None:
        raise WatchlistConflictError("watchlist item already exists")

    row = UserWatchlistItem(
        user_id=user_id,
        ts_code=normalized_ts_code,
        hourly_sync_enabled=payload.hourly_sync_enabled,
        daily_analysis_enabled=payload.daily_analysis_enabled,
        web_search_enabled=payload.web_search_enabled,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return await _serialize_watchlist_item(session, row)


async def update_watchlist_item(
    session: AsyncSession,
    *,
    user_id: str,
    ts_code: str,
    payload: WatchlistItemUpdateRequest,
) -> dict[str, object]:
    normalized_ts_code = ts_code.strip().upper()
    row = await _load_watchlist_item(
        session,
        user_id=user_id,
        ts_code=normalized_ts_code,
    )
    if row is None:
        raise WatchlistNotFoundError("watchlist item not found")

    if payload.hourly_sync_enabled is not None:
        row.hourly_sync_enabled = payload.hourly_sync_enabled
    if payload.daily_analysis_enabled is not None:
        row.daily_analysis_enabled = payload.daily_analysis_enabled
    if payload.web_search_enabled is not None:
        row.web_search_enabled = payload.web_search_enabled

    await session.commit()
    await session.refresh(row)
    return await _serialize_watchlist_item(session, row)


async def delete_watchlist_item(
    session: AsyncSession,
    *,
    user_id: str,
    ts_code: str,
) -> None:
    normalized_ts_code = ts_code.strip().upper()
    row = await _load_watchlist_item(
        session,
        user_id=user_id,
        ts_code=normalized_ts_code,
    )
    if row is None:
        raise WatchlistNotFoundError("watchlist item not found")

    await session.delete(row)
    await session.commit()


async def get_watchlist_feed(
    session: AsyncSession, *, user_id: str
) -> dict[str, object]:
    statement = (
        select(UserWatchlistItem)
        .where(UserWatchlistItem.user_id == user_id)
        .order_by(UserWatchlistItem.updated_at.desc())
    )
    items = (await session.execute(statement)).scalars().all()
    payload: list[dict[str, object]] = []
    for item in items:
        instrument = await load_stock_instrument(session, item.ts_code)
        latest_report = await load_latest_report(session, item.ts_code)
        payload.append(
            {
                "ts_code": item.ts_code,
                "instrument": instrument,
                "latest_report": (
                    serialize_report_archive_item(latest_report)
                    if latest_report is not None
                    else None
                ),
                "last_hourly_sync_at": item.last_hourly_sync_at,
                "last_daily_analysis_at": item.last_daily_analysis_at,
            }
        )

    return WatchlistFeedResponse(items=payload).model_dump()
