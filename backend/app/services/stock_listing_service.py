from collections.abc import Awaitable, Callable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_instrument import StockInstrument
from app.schemas.stocks import StockDailySnapshotResponse, StockListItemResponse


StockQuoteLoader = Callable[
    [list[str]], Awaitable[dict[str, StockDailySnapshotResponse]]
]


def _is_quote_complete(value: StockDailySnapshotResponse | None) -> bool:
    if value is None:
        return False
    # 只要收盘价与交易日齐全即可认为“足够展示”。
    return value.close is not None and value.trade_date is not None


async def list_stock_items_with_quote_completion(
    *,
    session: AsyncSession,
    keyword: str | None,
    list_statuses: list[str],
    page: int,
    page_size: int,
    load_latest_snapshots: StockQuoteLoader,
    load_latest_daily_kline: StockQuoteLoader,
    fetch_latest_tushare: StockQuoteLoader,
) -> list[StockListItemResponse]:
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

    ts_codes = [instrument.ts_code for instrument in instruments]
    quote_by_ts_code = await load_latest_snapshots(ts_codes)

    # 关键流程：优先使用本地快照，缺失时再回退到 kline 与 Tushare，
    # 这样可以在保证展示完整性的同时，尽量减少三方接口调用。
    missing_after_snapshot = [
        ts_code
        for ts_code in ts_codes
        if not _is_quote_complete(quote_by_ts_code.get(ts_code))
    ]
    if missing_after_snapshot:
        kline_quote_by_ts_code = await load_latest_daily_kline(missing_after_snapshot)
        for ts_code, quote in kline_quote_by_ts_code.items():
            if _is_quote_complete(quote):
                quote_by_ts_code[ts_code] = quote

    missing_after_kline = [
        ts_code
        for ts_code in ts_codes
        if not _is_quote_complete(quote_by_ts_code.get(ts_code))
    ]
    if missing_after_kline:
        # 最后回退到三方行情补齐，尽量减少接口调用范围。
        tushare_quote_by_ts_code = await fetch_latest_tushare(missing_after_kline)
        for ts_code, quote in tushare_quote_by_ts_code.items():
            if _is_quote_complete(quote):
                quote_by_ts_code[ts_code] = quote

    result: list[StockListItemResponse] = []
    for instrument in instruments:
        latest_snapshot = quote_by_ts_code.get(instrument.ts_code)
        result.append(
            StockListItemResponse(
                ts_code=instrument.ts_code,
                symbol=instrument.symbol,
                name=instrument.name,
                fullname=instrument.fullname,
                exchange=instrument.exchange,
                close=(latest_snapshot.close if latest_snapshot is not None else None),
                pct_chg=(
                    latest_snapshot.pct_chg if latest_snapshot is not None else None
                ),
                trade_date=(
                    latest_snapshot.trade_date if latest_snapshot is not None else None
                ),
            )
        )

    return result
