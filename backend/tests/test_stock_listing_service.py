import asyncio
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.stock_instrument import StockInstrument
from app.schemas.stocks import StockDailySnapshotResponse
from app.services.stock_listing_service import list_stock_items_with_quote_completion


def _quote(
    ts_code: str, close: float, pct_chg: float, trade_date: date
) -> StockDailySnapshotResponse:
    return StockDailySnapshotResponse(
        ts_code=ts_code,
        trade_date=trade_date,
        open=None,
        high=None,
        low=None,
        close=close,
        pre_close=None,
        change=None,
        pct_chg=pct_chg,
        vol=None,
        amount=None,
        turnover_rate=None,
        volume_ratio=None,
        pe=None,
        pb=None,
        total_mv=None,
        circ_mv=None,
    )


@pytest.fixture
def listing_session_maker(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "stock-listing-service.db")
    init_sqlite_schema(engine)
    yield session_maker


def test_listing_service_applies_snapshot_kline_tushare_fallback_chain(
    listing_session_maker: async_sessionmaker,
) -> None:
    async def _run() -> None:
        async with listing_session_maker() as session:
            session.add_all(
                [
                    StockInstrument(
                        ts_code="000001.SZ",
                        symbol="000001",
                        name="平安银行",
                        fullname="平安银行股份有限公司",
                        exchange="SZSE",
                        list_status="L",
                    ),
                    StockInstrument(
                        ts_code="000002.SZ",
                        symbol="000002",
                        name="万科A",
                        fullname="万科企业股份有限公司",
                        exchange="SZSE",
                        list_status="L",
                    ),
                    StockInstrument(
                        ts_code="000003.SZ",
                        symbol="000003",
                        name="国华网安",
                        fullname="国华网安科技股份有限公司",
                        exchange="SZSE",
                        list_status="L",
                    ),
                ]
            )
            await session.commit()

            calls: dict[str, list[list[str]]] = {
                "snapshot": [],
                "kline": [],
                "tushare": [],
            }

            async def load_latest_snapshots(
                ts_codes: list[str],
            ) -> dict[str, StockDailySnapshotResponse]:
                calls["snapshot"].append(ts_codes)
                return {
                    "000001.SZ": _quote("000001.SZ", 11.1, 1.2, date(2026, 3, 3)),
                }

            async def load_latest_daily_kline(
                ts_codes: list[str],
            ) -> dict[str, StockDailySnapshotResponse]:
                calls["kline"].append(ts_codes)
                return {
                    "000002.SZ": _quote("000002.SZ", 22.2, -0.8, date(2026, 3, 3)),
                }

            async def fetch_latest_tushare(
                ts_codes: list[str],
            ) -> dict[str, StockDailySnapshotResponse]:
                calls["tushare"].append(ts_codes)
                return {
                    "000003.SZ": _quote("000003.SZ", 33.3, 2.6, date(2026, 3, 3)),
                }

            result = await list_stock_items_with_quote_completion(
                session=session,
                keyword=None,
                list_statuses=["L"],
                page=1,
                page_size=20,
                load_latest_snapshots=load_latest_snapshots,
                load_latest_daily_kline=load_latest_daily_kline,
                fetch_latest_tushare=fetch_latest_tushare,
            )

            assert [item.ts_code for item in result] == [
                "000001.SZ",
                "000002.SZ",
                "000003.SZ",
            ]
            assert [item.close for item in result] == [11.1, 22.2, 33.3]
            assert calls["snapshot"] == [["000001.SZ", "000002.SZ", "000003.SZ"]]
            assert calls["kline"] == [["000002.SZ", "000003.SZ"]]
            assert calls["tushare"] == [["000003.SZ"]]

    asyncio.run(_run())


def test_listing_service_applies_keyword_status_and_pagination(
    listing_session_maker: async_sessionmaker,
) -> None:
    async def _run() -> None:
        async with listing_session_maker() as session:
            session.add_all(
                [
                    StockInstrument(
                        ts_code="000004.SZ",
                        symbol="000004",
                        name="国华网安",
                        fullname="国华网安科技股份有限公司",
                        exchange="SZSE",
                        list_status="L",
                    ),
                    StockInstrument(
                        ts_code="000001.SZ",
                        symbol="000001",
                        name="平安银行",
                        fullname="平安银行股份有限公司",
                        exchange="SZSE",
                        list_status="L",
                    ),
                    StockInstrument(
                        ts_code="000002.SZ",
                        symbol="000002",
                        name="万科A",
                        fullname="万科企业股份有限公司",
                        exchange="SZSE",
                        list_status="D",
                    ),
                ]
            )
            await session.commit()

            async def load_empty(
                ts_codes: list[str],
            ) -> dict[str, StockDailySnapshotResponse]:
                _ = ts_codes
                return {}

            result = await list_stock_items_with_quote_completion(
                session=session,
                keyword="平安",
                list_statuses=["L"],
                page=1,
                page_size=1,
                load_latest_snapshots=load_empty,
                load_latest_daily_kline=load_empty,
                fetch_latest_tushare=load_empty,
            )

            assert len(result) == 1
            assert result[0].ts_code == "000001.SZ"
            assert result[0].name == "平安银行"

    asyncio.run(_run())
