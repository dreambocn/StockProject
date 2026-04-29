import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.stock_instrument import StockInstrument
from app.models.stock_kline_bar import StockKlineBar
from app.services.stock_quote_service import (
    load_price_windows_with_completion,
    load_price_window_with_completion,
    load_resolved_latest_snapshot,
)


def _setup_async_session(tmp_path: Path):
    db_path = tmp_path / 'stock-quote-service.db'
    db_url = f'sqlite+aiosqlite:///{db_path.as_posix()}'
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


def test_load_resolved_latest_snapshot_falls_back_to_daily_kline_db(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    remote_calls = {'count': 0}

    async def fake_fetch_latest_quotes(_ts_codes: list[str]):
        remote_calls['count'] += 1
        return {}

    async def run_test() -> None:
        async with session_maker() as session:
            session.add(
                StockInstrument(
                    ts_code='600519.SH',
                    symbol='600519',
                    name='贵州茅台',
                    fullname='贵州茅台酒股份有限公司',
                    list_status='L',
                )
            )
            session.add(
                StockKlineBar(
                    ts_code='600519.SH',
                    period='daily',
                    trade_date=date(2026, 3, 31),
                    end_date=None,
                    open=Decimal('1498.00'),
                    high=Decimal('1512.00'),
                    low=Decimal('1490.00'),
                    close=Decimal('1508.50'),
                    pre_close=Decimal('1496.00'),
                    change=Decimal('12.50'),
                    pct_chg=Decimal('0.8356'),
                    vol=Decimal('123456'),
                    amount=Decimal('789012'),
                )
            )
            await session.commit()

            snapshot = await load_resolved_latest_snapshot(
                session,
                ts_code='600519.SH',
                fetch_latest_quotes_fn=fake_fetch_latest_quotes,
            )

            assert snapshot is not None
            assert snapshot.trade_date.isoformat() == '2026-03-31'
            assert snapshot.close == 1508.5
            assert snapshot.pct_chg == 0.8356
            assert remote_calls['count'] == 0

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_price_window_with_completion_fetches_and_persists_daily_kline_rows(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    captured_args: dict[str, object] = {}

    async def fake_fetch_daily_by_range(*, ts_code: str, start_date: str, end_date: str):
        captured_args['ts_code'] = ts_code
        captured_args['start_date'] = start_date
        captured_args['end_date'] = end_date
        return [
            {
                'ts_code': ts_code,
                'trade_date': '20260320',
                'open': 10.0,
                'high': 10.2,
                'low': 9.9,
                'close': 10.1,
                'pre_close': 9.8,
                'change': 0.3,
                'pct_chg': 3.06,
                'vol': 100000,
                'amount': 500000,
            },
            {
                'ts_code': ts_code,
                'trade_date': '20260321',
                'open': 10.1,
                'high': 10.4,
                'low': 10.0,
                'close': 10.3,
                'pre_close': 10.1,
                'change': 0.2,
                'pct_chg': 1.98,
                'vol': 110000,
                'amount': 520000,
            },
            {
                'ts_code': ts_code,
                'trade_date': '20260324',
                'open': 10.3,
                'high': 10.5,
                'low': 10.2,
                'close': 10.4,
                'pre_close': 10.3,
                'change': 0.1,
                'pct_chg': 0.97,
                'vol': 120000,
                'amount': 540000,
            },
            {
                'ts_code': ts_code,
                'trade_date': '20260325',
                'open': 10.4,
                'high': 10.7,
                'low': 10.3,
                'close': 10.6,
                'pre_close': 10.4,
                'change': 0.2,
                'pct_chg': 1.92,
                'vol': 130000,
                'amount': 560000,
            },
            {
                'ts_code': ts_code,
                'trade_date': '20260326',
                'open': 10.6,
                'high': 10.8,
                'low': 10.5,
                'close': 10.7,
                'pre_close': 10.6,
                'change': 0.1,
                'pct_chg': 0.94,
                'vol': 140000,
                'amount': 580000,
            },
        ]

    async def run_test() -> None:
        async with session_maker() as session:
            session.add(
                StockInstrument(
                    ts_code='000001.SZ',
                    symbol='000001',
                    name='平安银行',
                    fullname='平安银行股份有限公司',
                    list_status='L',
                )
            )
            await session.commit()

            rows = await load_price_window_with_completion(
                session,
                ts_code='000001.SZ',
                anchor_from=date(2026, 3, 20),
                window_size=5,
                fetch_daily_by_range_fn=fake_fetch_daily_by_range,
            )

            assert len(rows) == 5
            assert rows[0]['trade_date'].isoformat() == '2026-03-20'
            assert rows[-1]['trade_date'].isoformat() == '2026-03-26'
            assert captured_args == {
                'ts_code': '000001.SZ',
                'start_date': '20260320',
                'end_date': '20260419',
            }

            persisted_rows = (
                await session.execute(
                    select(StockKlineBar).where(
                        StockKlineBar.ts_code == '000001.SZ',
                        StockKlineBar.period == 'daily',
                    )
                )
            ).scalars().all()
            assert len(persisted_rows) == 5

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_price_windows_with_completion_fetches_once_for_multiple_anchor_dates(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)
    captured_calls: list[dict[str, str]] = []

    async def fake_fetch_daily_by_range(*, ts_code: str, start_date: str, end_date: str):
        captured_calls.append(
            {
                'ts_code': ts_code,
                'start_date': start_date,
                'end_date': end_date,
            }
        )
        return [
            {
                'ts_code': ts_code,
                'trade_date': trade_date,
                'open': 10.0 + index,
                'high': 10.2 + index,
                'low': 9.9 + index,
                'close': 10.1 + index,
                'pre_close': 9.8 + index,
                'change': 0.3,
                'pct_chg': 3.06,
                'vol': 100000 + index,
                'amount': 500000 + index,
            }
            for index, trade_date in enumerate(
                [
                    '20260320',
                    '20260321',
                    '20260324',
                    '20260325',
                    '20260326',
                    '20260327',
                    '20260330',
                ]
            )
        ]

    async def run_test() -> None:
        async with session_maker() as session:
            session.add(
                StockInstrument(
                    ts_code='000001.SZ',
                    symbol='000001',
                    name='平安银行',
                    fullname='平安银行股份有限公司',
                    list_status='L',
                )
            )
            await session.commit()

            windows = await load_price_windows_with_completion(
                session,
                ts_code='000001.SZ',
                anchor_dates=[date(2026, 3, 20), date(2026, 3, 24)],
                window_size=3,
                fetch_daily_by_range_fn=fake_fetch_daily_by_range,
            )

            assert [row['trade_date'].isoformat() for row in windows[date(2026, 3, 20)]] == [
                '2026-03-20',
                '2026-03-21',
                '2026-03-24',
            ]
            assert [row['trade_date'].isoformat() for row in windows[date(2026, 3, 24)]] == [
                '2026-03-24',
                '2026-03-25',
                '2026-03-26',
            ]
            assert captured_calls == [
                {
                    'ts_code': '000001.SZ',
                    'start_date': '20260320',
                    'end_date': '20260423',
                }
            ]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
