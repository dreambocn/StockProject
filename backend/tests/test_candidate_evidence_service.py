import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.stock_candidate_evidence_cache import StockCandidateEvidenceCache
from app.models.stock_instrument import StockInstrument
from app.services.candidate_evidence_service import (
    HOT_SEARCH_CACHE_KEY,
    RESEARCH_REPORT_CACHE_KEY,
    get_candidate_evidence_snapshots,
    refresh_candidate_evidence_caches,
)


class FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        _ = ex
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        if key not in self._store:
            return 0
        del self._store[key]
        return 1


def _build_session_factory(tmp_path: Path) -> async_sessionmaker:
    db_path = tmp_path / "candidate-evidence-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            session.add_all(
                [
                    StockInstrument(
                        ts_code="600938.SH",
                        symbol="600938",
                        name="中国海油",
                        fullname="中国海洋石油有限公司",
                        area="北京",
                        industry="石油开采",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(2022, 4, 21),
                        delist_date=None,
                        is_hs="N",
                    ),
                    StockInstrument(
                        ts_code="600547.SH",
                        symbol="600547",
                        name="山东黄金",
                        fullname="山东黄金矿业股份有限公司",
                        area="山东",
                        industry="黄金",
                        market="主板",
                        exchange="SSE",
                        list_status="L",
                        list_date=date(2003, 8, 28),
                        delist_date=None,
                        is_hs="N",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(_prepare())
    return session_maker


def test_candidate_evidence_service_aggregates_hot_search_and_research_rows(
    tmp_path: Path,
) -> None:
    session_maker = _build_session_factory(tmp_path)
    redis_client = FakeRedisClient()

    async def _run() -> None:
        async with session_maker() as session:
            snapshots = await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH", "600547.SH"],
                now=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
                redis_client_getter=lambda: redis_client,
                fetch_hot_search_rows=lambda: _async_value(
                    [
                        {
                            "股票代码": "600938",
                            "股票名称": "中国海油",
                            "当前排名": 1,
                            "搜索指数": 980123,
                        }
                    ]
                ),
                fetch_research_report_rows=lambda: _async_value(
                    [
                        {
                            "股票代码": "600547",
                            "股票简称": "山东黄金",
                            "报告日期": "2026-03-20",
                            "报告标题": "金价上行驱动盈利弹性释放",
                            "机构": "中信证券",
                            "东财评级": "买入",
                        }
                    ]
                ),
            )

            assert snapshots["600938.SH"].hot_search_count == 1
            assert snapshots["600938.SH"].research_report_count == 0
            assert snapshots["600938.SH"].evidence_items[0].evidence_kind == "hot_search"
            assert snapshots["600547.SH"].research_report_count == 1
            assert snapshots["600547.SH"].evidence_items[0].title == "金价上行驱动盈利弹性释放"
            assert snapshots["600547.SH"].latest_published_at == datetime(
                2026, 3, 20, 0, 0, tzinfo=UTC
            )

    asyncio.run(_run())


def test_candidate_evidence_service_uses_cache_before_refetching(
    tmp_path: Path,
) -> None:
    session_maker = _build_session_factory(tmp_path)
    redis_client = FakeRedisClient()
    hot_calls = {"count": 0}
    report_calls = {"count": 0}

    async def fake_hot_rows() -> list[dict[str, object]]:
        hot_calls["count"] += 1
        return [
            {
                "股票代码": "600938",
                "股票名称": "中国海油",
                "当前排名": 2,
                "搜索指数": 870000,
            }
        ]

    async def fake_report_rows() -> list[dict[str, object]]:
        report_calls["count"] += 1
        return [
            {
                "股票代码": "600547",
                "股票简称": "山东黄金",
                "报告日期": "2026-03-19",
                "报告标题": "盈利修复趋势明确",
                "机构": "国泰君安",
                "东财评级": "增持",
            }
        ]

    async def _run() -> None:
        async with session_maker() as session:
            first = await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH", "600547.SH"],
                now=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
                redis_client_getter=lambda: redis_client,
                fetch_hot_search_rows=fake_hot_rows,
                fetch_research_report_rows=fake_report_rows,
            )
            second = await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH", "600547.SH"],
                now=datetime(2026, 3, 24, 9, 10, tzinfo=UTC),
                redis_client_getter=lambda: redis_client,
                fetch_hot_search_rows=fake_hot_rows,
                fetch_research_report_rows=fake_report_rows,
            )

            assert first["600938.SH"].hot_search_count == 1
            assert second["600547.SH"].research_report_count == 1
            assert hot_calls["count"] == 1
            assert report_calls["count"] == 1

    asyncio.run(_run())


def test_candidate_evidence_service_falls_back_to_db_when_upstream_fails(
    tmp_path: Path,
) -> None:
    session_maker = _build_session_factory(tmp_path)

    async def _run() -> None:
        async with session_maker() as session:
            warm_cache_redis = FakeRedisClient()
            stale_redis = FakeRedisClient()

            await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH"],
                now=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
                redis_client_getter=lambda: warm_cache_redis,
                fetch_hot_search_rows=lambda: _async_value(
                    [
                        {
                            "股票代码": "600938",
                            "股票名称": "中国海油",
                            "当前排名": 3,
                            "搜索指数": 650000,
                        }
                    ]
                ),
                fetch_research_report_rows=lambda: _async_value([]),
            )

            snapshots = await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH"],
                now=datetime(2026, 3, 26, 12, 0, tzinfo=UTC),
                redis_client_getter=lambda: stale_redis,
                fetch_hot_search_rows=_raise_upstream_error,
                fetch_research_report_rows=_raise_upstream_error,
                hot_search_refresh_window_seconds=3600,
                research_report_refresh_window_seconds=3600,
            )

            assert snapshots["600938.SH"].hot_search_count == 1
            assert snapshots["600938.SH"].evidence_items[0].summary

    asyncio.run(_run())


def test_candidate_evidence_service_filters_research_reports_by_recent_30_days(
    tmp_path: Path,
) -> None:
    session_maker = _build_session_factory(tmp_path)
    redis_client = FakeRedisClient()

    async def _run() -> None:
        async with session_maker() as session:
            snapshots = await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600547.SH"],
                now=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
                redis_client_getter=lambda: redis_client,
                fetch_hot_search_rows=lambda: _async_value([]),
                fetch_research_report_rows=lambda: _async_value(
                    [
                        {
                            "股票代码": "600547",
                            "股票简称": "山东黄金",
                            "报告日期": "2026-03-18",
                            "报告标题": "近30日有效研报",
                            "机构": "中信建投",
                            "东财评级": "买入",
                        },
                        {
                            "股票代码": "600547",
                            "股票简称": "山东黄金",
                            "报告日期": "2026-02-20",
                            "报告标题": "超过30日无效研报",
                            "机构": "国海证券",
                            "东财评级": "增持",
                        },
                        {
                            "股票代码": "600547",
                            "股票简称": "山东黄金",
                            "报告标题": "缺失日期无效研报",
                            "机构": "华泰证券",
                            "东财评级": "中性",
                        },
                    ]
                ),
            )

            snapshot = snapshots["600547.SH"]
            assert snapshot.research_report_count == 1
            assert len(snapshot.source_breakdown) == 1
            assert snapshot.source_breakdown[0].source == "research_report"
            assert snapshot.source_breakdown[0].count == 1
            assert len(snapshot.evidence_items) == 1
            assert snapshot.evidence_items[0].title == "近30日有效研报"
            assert snapshot.latest_published_at == datetime(
                2026, 3, 18, 0, 0, tzinfo=UTC
            )

    asyncio.run(_run())


def test_candidate_evidence_service_uses_default_redis_getter_for_cache_io(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_maker = _build_session_factory(tmp_path)
    redis_client = FakeRedisClient()

    async def _run() -> None:
        async with session_maker() as session:
            await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH"],
                now=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
                fetch_hot_search_rows=lambda: _async_value(
                    [
                        {
                            "股票代码": "600938",
                            "股票名称": "中国海油",
                            "当前排名": 1,
                            "搜索指数": 980123,
                        }
                    ]
                ),
                fetch_research_report_rows=lambda: _async_value([]),
            )

    # 关键回归：默认路径必须使用真实 Redis getter，而不是返回 None 的占位函数。
    monkeypatch.setattr(
        "app.services.candidate_evidence_service.get_redis_client",
        lambda: redis_client,
    )

    asyncio.run(_run())

    assert HOT_SEARCH_CACHE_KEY in redis_client._store


def test_refresh_candidate_evidence_caches_archives_history_and_keeps_latest_batch(
    tmp_path: Path,
) -> None:
    session_maker = _build_session_factory(tmp_path)
    redis_client = FakeRedisClient()

    async def _run() -> None:
        async with session_maker() as session:
            await refresh_candidate_evidence_caches(
                session=session,
                now=datetime(2026, 3, 24, 0, 5, tzinfo=UTC),
                redis_client_getter=lambda: redis_client,
                fetch_hot_search_rows=lambda: _async_value(
                    [
                        {
                            "股票代码": "600938",
                            "股票名称": "中国海油",
                            "当前排名": 5,
                            "搜索指数": 600000,
                        }
                    ]
                ),
                fetch_research_report_rows=lambda: _async_value([]),
                include_research_report=False,
            )
            await refresh_candidate_evidence_caches(
                session=session,
                now=datetime(2026, 3, 24, 1, 5, tzinfo=UTC),
                redis_client_getter=lambda: redis_client,
                fetch_hot_search_rows=lambda: _async_value(
                    [
                        {
                            "股票代码": "600938",
                            "股票名称": "中国海油",
                            "当前排名": 2,
                            "搜索指数": 900000,
                        }
                    ]
                ),
                fetch_research_report_rows=lambda: _async_value([]),
                include_research_report=False,
            )

            archive_rows = (
                await session.execute(
                    select(StockCandidateEvidenceCache).where(
                        StockCandidateEvidenceCache.evidence_kind == "hot_search"
                    )
                )
            ).scalars().all()
            assert len(archive_rows) == 2

            snapshots = await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH"],
                now=datetime(2026, 3, 24, 2, 0, tzinfo=UTC),
                redis_client_getter=lambda: redis_client,
                allow_remote_fetch=False,
            )

            assert snapshots["600938.SH"].hot_search_count == 1
            assert snapshots["600938.SH"].evidence_items[0].summary == "百度热搜排名第 2 位；搜索热度 900000"
            assert HOT_SEARCH_CACHE_KEY in redis_client._store

    asyncio.run(_run())


def test_candidate_evidence_service_uses_db_latest_batch_when_remote_fetch_disabled(
    tmp_path: Path,
) -> None:
    session_maker = _build_session_factory(tmp_path)

    async def _run() -> None:
        async with session_maker() as session:
            warm_redis = FakeRedisClient()
            stale_redis = FakeRedisClient()
            hot_calls = {"count": 0}
            report_calls = {"count": 0}

            async def fake_hot_rows() -> list[dict[str, object]]:
                hot_calls["count"] += 1
                return [
                    {
                        "股票代码": "600938",
                        "股票名称": "中国海油",
                        "当前排名": 1,
                        "搜索指数": 990000,
                    }
                ]

            async def fake_report_rows() -> list[dict[str, object]]:
                report_calls["count"] += 1
                return []

            await refresh_candidate_evidence_caches(
                session=session,
                now=datetime(2026, 3, 24, 0, 5, tzinfo=UTC),
                redis_client_getter=lambda: warm_redis,
                fetch_hot_search_rows=fake_hot_rows,
                fetch_research_report_rows=fake_report_rows,
                include_research_report=False,
            )
            hot_calls["count"] = 0
            report_calls["count"] = 0

            snapshots = await get_candidate_evidence_snapshots(
                session=session,
                ts_codes=["600938.SH"],
                now=datetime(2026, 3, 26, 12, 0, tzinfo=UTC),
                redis_client_getter=lambda: stale_redis,
                allow_remote_fetch=False,
                fetch_hot_search_rows=fake_hot_rows,
                fetch_research_report_rows=fake_report_rows,
                hot_search_refresh_window_seconds=3600,
                research_report_refresh_window_seconds=3600,
            )

            assert snapshots["600938.SH"].hot_search_count == 1
            assert hot_calls["count"] == 0
            assert report_calls["count"] == 0
            assert RESEARCH_REPORT_CACHE_KEY not in stale_redis._store

    asyncio.run(_run())


async def _async_value(value):
    return value


async def _raise_upstream_error() -> list[dict[str, object]]:
    raise RuntimeError("upstream failed")
