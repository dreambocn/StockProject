import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.services.stock_repository import (
    load_adj_factor_rows_from_db,
    load_kline_rows_from_db,
    load_latest_daily_kline_map,
    load_latest_snapshots_map,
    load_trade_cal_rows_from_db,
    upsert_adj_factor_rows,
    upsert_kline_rows,
    upsert_trade_cal_rows,
)


def _with_session_maker(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "stock-repository-test.db")
    init_sqlite_schema(engine)
    return session_maker, engine


def test_kline_and_snapshot_repository_helpers(tmp_path: Path) -> None:
    session_maker, engine = _with_session_maker(tmp_path)

    async def _run() -> None:
        async with session_maker() as session:
            await upsert_kline_rows(
                session=session,
                ts_code="000001.SZ",
                period="daily",
                rows=[
                    {
                        "trade_date": "20260303",
                        "open": 11.0,
                        "high": 11.2,
                        "low": 10.8,
                        "close": 11.1,
                        "pre_close": 10.95,
                        "change": 0.15,
                        "pct_chg": 1.37,
                        "vol": 123456,
                        "amount": 789012,
                    }
                ],
            )
            session.add(
                StockDailySnapshot(
                    ts_code="000001.SZ",
                    trade_date=date(2026, 3, 2),
                    open=Decimal("10.9"),
                    high=Decimal("11.0"),
                    low=Decimal("10.7"),
                    close=Decimal("10.95"),
                    pre_close=Decimal("10.9"),
                    change=Decimal("0.05"),
                    pct_chg=Decimal("0.46"),
                    vol=Decimal("100000"),
                    amount=Decimal("700000"),
                    turnover_rate=Decimal("1.0"),
                    volume_ratio=Decimal("1.0"),
                    pe=Decimal("6.0"),
                    pb=Decimal("0.7"),
                    total_mv=Decimal("1000000"),
                    circ_mv=Decimal("900000"),
                )
            )
            await session.commit()

            kline_rows = await load_kline_rows_from_db(
                session=session,
                ts_code="000001.SZ",
                period="daily",
                start_date="20260301",
                end_date="20260305",
                limit=5,
            )
            assert len(kline_rows) == 1
            assert kline_rows[0].trade_date.isoformat() == "2026-03-03"
            assert kline_rows[0].close == 11.1

            latest_kline_map = await load_latest_daily_kline_map(
                session=session,
                ts_codes=["000001.SZ"],
            )
            assert latest_kline_map["000001.SZ"].trade_date.isoformat() == "2026-03-03"

            latest_snapshot_map = await load_latest_snapshots_map(
                session=session,
                ts_codes=["000001.SZ"],
            )
            assert (
                latest_snapshot_map["000001.SZ"].trade_date.isoformat() == "2026-03-02"
            )

    asyncio.run(_run())


def test_trade_calendar_repository_helpers(tmp_path: Path) -> None:
    session_maker, engine = _with_session_maker(tmp_path)

    async def _run() -> None:
        async with session_maker() as session:
            await upsert_trade_cal_rows(
                session=session,
                exchange="SSE",
                rows=[
                    {
                        "cal_date": "20260303",
                        "is_open": "1",
                        "pretrade_date": "20260302",
                    }
                ],
            )
            await session.commit()

            rows = await load_trade_cal_rows_from_db(
                session=session,
                exchange="SSE",
                start_date="20260301",
                end_date="20260305",
                is_open="1",
            )
            assert len(rows) == 1
            assert rows[0].cal_date.isoformat() == "2026-03-03"
            assert rows[0].is_open == "1"

    asyncio.run(_run())


def test_adj_factor_repository_helpers(tmp_path: Path) -> None:
    session_maker, engine = _with_session_maker(tmp_path)

    async def _run() -> None:
        async with session_maker() as session:
            await upsert_adj_factor_rows(
                session=session,
                ts_code="000001.SZ",
                rows=[
                    {
                        "trade_date": "20260303",
                        "adj_factor": 1.2345,
                    }
                ],
            )
            await session.commit()

            rows_by_range = await load_adj_factor_rows_from_db(
                session=session,
                ts_code="000001.SZ",
                start_date="20260301",
                end_date="20260305",
                trade_date=None,
                limit=10,
            )
            assert len(rows_by_range) == 1
            assert rows_by_range[0].adj_factor == 1.2345

            rows_by_trade_date = await load_adj_factor_rows_from_db(
                session=session,
                ts_code="000001.SZ",
                start_date="20260301",
                end_date="20260305",
                trade_date="20260303",
                limit=10,
            )
            assert len(rows_by_trade_date) == 1
            assert rows_by_trade_date[0].trade_date.isoformat() == "2026-03-03"

    asyncio.run(_run())
