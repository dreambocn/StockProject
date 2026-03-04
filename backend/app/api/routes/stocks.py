from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.integrations.tushare_gateway import TushareGateway
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.user import User
from app.schemas.stocks import (
    StockBasicSyncResponse,
    StockDailySnapshotResponse,
    StockDetailResponse,
    StockInstrumentResponse,
    StockListItemResponse,
)
from app.services.stock_sync_service import (
    STOCK_BASIC_FULL_STATUSES,
    sync_stock_basic_full,
)


router = APIRouter()


def _parse_list_status_filter(value: str) -> list[str]:
    normalized_value = value.strip().upper()
    if not normalized_value:
        return ["L"]
    if normalized_value == "ALL":
        return list(STOCK_BASIC_FULL_STATUSES)

    parsed: list[str] = []
    seen: set[str] = set()
    for raw_status in normalized_value.split(","):
        status_value = raw_status.strip()[:1]
        if status_value not in STOCK_BASIC_FULL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid list_status, expected ALL or comma-separated values in L,D,P,G",
            )
        if status_value in seen:
            continue
        seen.add(status_value)
        parsed.append(status_value)

    return parsed or ["L"]


async def _fetch_latest_snapshot(
    session: AsyncSession, ts_code: str
) -> StockDailySnapshot | None:
    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == ts_code)
        .order_by(StockDailySnapshot.trade_date.desc())
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_daily_snapshot_response(
    snapshot: StockDailySnapshot,
) -> StockDailySnapshotResponse:
    return StockDailySnapshotResponse(
        ts_code=snapshot.ts_code,
        trade_date=snapshot.trade_date,
        open=_to_float(snapshot.open),
        high=_to_float(snapshot.high),
        low=_to_float(snapshot.low),
        close=_to_float(snapshot.close),
        pre_close=_to_float(snapshot.pre_close),
        change=_to_float(snapshot.change),
        pct_chg=_to_float(snapshot.pct_chg),
        vol=_to_float(snapshot.vol),
        amount=_to_float(snapshot.amount),
        turnover_rate=_to_float(snapshot.turnover_rate),
        volume_ratio=_to_float(snapshot.volume_ratio),
        pe=_to_float(snapshot.pe),
        pb=_to_float(snapshot.pb),
        total_mv=_to_float(snapshot.total_mv),
        circ_mv=_to_float(snapshot.circ_mv),
    )


@router.get("/stocks", response_model=list[StockListItemResponse])
async def list_stocks(
    keyword: str | None = Query(default=None),
    list_status: str = Query(default="L"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockListItemResponse]:
    list_statuses = _parse_list_status_filter(list_status)
    statement = select(StockInstrument).where(
        StockInstrument.list_status.in_(list_statuses)
    )
    normalized_keyword = keyword.strip() if keyword else ""
    if normalized_keyword:
        wildcard = f"%{normalized_keyword}%"
        statement = statement.where(
            or_(
                StockInstrument.ts_code.ilike(wildcard),
                StockInstrument.symbol.ilike(wildcard),
                StockInstrument.name.ilike(wildcard),
            )
        )

    statement = (
        statement.order_by(StockInstrument.ts_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    instruments = (await session.execute(statement)).scalars().all()

    # 关键流程：列表查询始终补齐“最新交易日快照”，前端无需再发额外请求拼接卡片数据。
    result: list[StockListItemResponse] = []
    for instrument in instruments:
        latest_snapshot = await _fetch_latest_snapshot(session, instrument.ts_code)
        result.append(
            StockListItemResponse(
                ts_code=instrument.ts_code,
                symbol=instrument.symbol,
                name=instrument.name,
                fullname=instrument.fullname,
                exchange=instrument.exchange,
                close=(
                    _to_float(latest_snapshot.close)
                    if latest_snapshot is not None
                    else None
                ),
                pct_chg=(
                    _to_float(latest_snapshot.pct_chg)
                    if latest_snapshot is not None
                    else None
                ),
                trade_date=(
                    latest_snapshot.trade_date if latest_snapshot is not None else None
                ),
            )
        )

    return result


@router.post("/stocks/sync/full", response_model=StockBasicSyncResponse)
async def trigger_stock_basic_full_sync(
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
) -> StockBasicSyncResponse:
    # 鉴权边界：该接口会触发外部数据源全量同步，仅允许已登录用户调用。
    _ = current_user

    settings = get_settings()
    try:
        gateway = TushareGateway(settings.tushare_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tushare token not configured",
        ) from exc

    # 关键流程：全量基础库固定拉取 L/D/P/G，保证数据库主数据覆盖完整状态集合。
    sync_result = await sync_stock_basic_full(
        session,
        gateway,
        list_statuses=STOCK_BASIC_FULL_STATUSES,
    )
    return StockBasicSyncResponse(
        message="stock basic sync completed",
        total=int(sync_result["total"]),
        created=int(sync_result["created"]),
        updated=int(sync_result["updated"]),
        list_statuses=list(sync_result["list_statuses"]),
    )


@router.get("/stocks/{ts_code}", response_model=StockDetailResponse)
async def get_stock_detail(
    ts_code: str,
    session: AsyncSession = Depends(get_db_session),
) -> StockDetailResponse:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await session.get(StockInstrument, normalized_ts_code)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stock not found",
        )

    latest_snapshot = await _fetch_latest_snapshot(session, normalized_ts_code)
    return StockDetailResponse(
        instrument=StockInstrumentResponse.model_validate(instrument),
        latest_snapshot=(
            _to_daily_snapshot_response(latest_snapshot)
            if latest_snapshot is not None
            else None
        ),
    )


@router.get("/stocks/{ts_code}/daily", response_model=list[StockDailySnapshotResponse])
async def get_stock_daily(
    ts_code: str,
    limit: int = Query(default=60, ge=1, le=240),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockDailySnapshotResponse]:
    normalized_ts_code = ts_code.strip().upper()
    instrument = await session.get(StockInstrument, normalized_ts_code)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stock not found",
        )

    statement = (
        select(StockDailySnapshot)
        .where(StockDailySnapshot.ts_code == normalized_ts_code)
        .order_by(StockDailySnapshot.trade_date.desc())
        .limit(limit)
    )
    snapshots = (await session.execute(statement)).scalars().all()
    return [_to_daily_snapshot_response(snapshot) for snapshot in snapshots]
