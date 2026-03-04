import asyncio
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.stock_sync_cursor import StockSyncCursor
from app.services.stock_sync_service import (
    sync_recent_trade_days,
    sync_stock_basic_full,
)


class FakeTushareGateway:
    def __init__(self) -> None:
        self.requested_statuses: list[str] = []

    async def fetch_stock_basic_by_status(
        self, list_status: str
    ) -> list[dict[str, str]]:
        self.requested_statuses.append(list_status)
        payload_map: dict[str, list[dict[str, str]]] = {
            "L": [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "平安银行",
                    "area": "深圳",
                    "industry": "银行",
                    "fullname": "平安银行股份有限公司",
                    "enname": "Ping An Bank Co., Ltd.",
                    "cnspell": "PAYH",
                    "market": "主板",
                    "exchange": "SZSE",
                    "curr_type": "CNY",
                    "list_status": "L",
                    "list_date": "19910403",
                    "delist_date": "",
                    "is_hs": "S",
                    "act_name": "中国平安保险（集团）股份有限公司",
                    "act_ent_type": "中央国有企业",
                }
            ],
            "D": [
                {
                    "ts_code": "000004.SZ",
                    "symbol": "000004",
                    "name": "国农科技",
                    "area": "深圳",
                    "industry": "生物制药",
                    "fullname": "深圳中国农大科技股份有限公司",
                    "enname": "Shenzhen Cn-Agri Tech Co., Ltd.",
                    "cnspell": "GNKJ",
                    "market": "主板",
                    "exchange": "SZSE",
                    "curr_type": "CNY",
                    "list_status": "D",
                    "list_date": "19910114",
                    "delist_date": "20240130",
                    "is_hs": "N",
                    "act_name": "示例实控人",
                    "act_ent_type": "民营企业",
                }
            ],
            "P": [],
            "G": [
                {
                    "ts_code": "430001.BJ",
                    "symbol": "430001",
                    "name": "过会样本",
                    "area": "北京",
                    "industry": "软件服务",
                    "fullname": "过会样本科技股份有限公司",
                    "enname": "Pending Sample Tech Co., Ltd.",
                    "cnspell": "GHYB",
                    "market": "北交所",
                    "exchange": "BSE",
                    "curr_type": "CNY",
                    "list_status": "G",
                    "list_date": "",
                    "delist_date": "",
                    "is_hs": "N",
                    "act_name": "示例控股集团",
                    "act_ent_type": "地方国有企业",
                }
            ],
        }
        return payload_map.get(list_status, [])

    async def fetch_recent_open_trade_dates(self, limit: int) -> list[str]:
        assert limit == 120
        return ["20260303", "20260302"]

    async def fetch_daily_for_trade_date(
        self, trade_date: str
    ) -> list[dict[str, str | float]]:
        if trade_date == "20260303":
            return [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260303",
                    "open": 11.0,
                    "high": 11.2,
                    "low": 10.8,
                    "close": 11.1,
                    "pre_close": 10.95,
                    "change": 0.15,
                    "pct_chg": 1.37,
                    "vol": 123456.0,
                    "amount": 789012.0,
                }
            ]

        return [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260302",
                "open": 10.8,
                "high": 11.0,
                "low": 10.7,
                "close": 10.95,
                "pre_close": 10.7,
                "change": 0.25,
                "pct_chg": 2.33,
                "vol": 222222.0,
                "amount": 555555.0,
            }
        ]

    async def fetch_daily_basic_for_trade_date(
        self, trade_date: str
    ) -> list[dict[str, str | float]]:
        if trade_date == "20260303":
            return [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260303",
                    "turnover_rate": 1.2,
                    "volume_ratio": 0.9,
                    "pe": 6.1,
                    "pb": 0.7,
                    "total_mv": 1000000.0,
                    "circ_mv": 900000.0,
                }
            ]

        return [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260302",
                "turnover_rate": 1.1,
                "volume_ratio": 1.0,
                "pe": 6.0,
                "pb": 0.68,
                "total_mv": 990000.0,
                "circ_mv": 880000.0,
            }
        ]


def test_sync_recent_trade_days_persists_instruments_and_snapshots(tmp_path) -> None:
    db_file = tmp_path / "stock-sync.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        gateway = FakeTushareGateway()

        async with session_maker() as session:
            await sync_recent_trade_days(session, gateway, trade_days=120)

        async with session_maker() as session:
            instruments = (
                (await session.execute(select(StockInstrument))).scalars().all()
            )
            assert len(instruments) == 3
            assert {item.ts_code for item in instruments} == {
                "000001.SZ",
                "000004.SZ",
                "430001.BJ",
            }
            assert set(gateway.requested_statuses) == {"L", "D", "P", "G"}

            snapshots = (
                (await session.execute(select(StockDailySnapshot))).scalars().all()
            )
            assert len(snapshots) == 2

            latest = (
                await session.execute(
                    select(StockDailySnapshot).where(
                        StockDailySnapshot.trade_date == date(2026, 3, 3)
                    )
                )
            ).scalar_one()
            assert float(latest.close) == 11.1
            assert float(latest.turnover_rate) == 1.2

            cursor = (
                await session.execute(
                    select(StockSyncCursor).where(
                        StockSyncCursor.cursor_key == "daily_latest_trade_date"
                    )
                )
            ).scalar_one()
            assert cursor.cursor_value == "20260303"

        async with session_maker() as session:
            await sync_recent_trade_days(session, FakeTushareGateway(), trade_days=120)

        async with session_maker() as session:
            snapshot_count = await session.scalar(
                select(func.count()).select_from(StockDailySnapshot)
            )
            assert snapshot_count == 2

        await engine.dispose()

    asyncio.run(run_test())


def test_sync_stock_basic_full_persists_all_statuses(tmp_path) -> None:
    db_file = tmp_path / "stock-basic-full.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        gateway = FakeTushareGateway()

        async with session_maker() as session:
            first_result = await sync_stock_basic_full(session, gateway)

        assert first_result["total"] == 3
        assert first_result["created"] == 3
        assert first_result["updated"] == 0
        assert first_result["list_statuses"] == ["L", "D", "P", "G"]

        async with session_maker() as session:
            second_result = await sync_stock_basic_full(session, gateway)

        assert second_result["total"] == 3
        assert second_result["created"] == 0
        assert second_result["updated"] == 3

        async with session_maker() as session:
            instruments = (
                (await session.execute(select(StockInstrument))).scalars().all()
            )
            assert len(instruments) == 3
            listed = next(item for item in instruments if item.ts_code == "000001.SZ")
            assert listed.fullname == "平安银行股份有限公司"
            assert listed.curr_type == "CNY"
            assert listed.act_ent_type == "中央国有企业"

        await engine.dispose()

    asyncio.run(run_test())
