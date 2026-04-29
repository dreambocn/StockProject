import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.system_job_run import SystemJobRun
from app.services.stock_sync_service import sync_stock_basic_full


class FakeGateway:
    async def fetch_stock_basic_by_status(self, list_status: str) -> list[dict[str, str]]:
        if list_status == "L":
            return [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "平安银行",
                    "fullname": "平安银行股份有限公司",
                    "list_status": "L",
                }
            ]
        return []


def test_stock_sync_full_creates_system_job(tmp_path) -> None:
    db_file = tmp_path / "stock-sync-job.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "stock-sync-job.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            result = await sync_stock_basic_full(session, FakeGateway(), list_statuses=["L"])
            assert result["total"] == 1

            job = (
                await session.execute(select(SystemJobRun).limit(1))
            ).scalar_one()
            assert job.job_type == "stock_sync_full"
            assert job.status == "success"
            assert job.metrics_json["created"] == 1
            assert job.metrics_json["list_statuses"] == ["L"]


    asyncio.run(run_test())
