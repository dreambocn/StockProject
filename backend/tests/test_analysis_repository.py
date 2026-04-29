import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.analysis_agent_run import AnalysisAgentRun
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.services.analysis_repository import (
    claim_next_analysis_session_for_worker,
    list_analysis_agent_runs_for_reports,
    load_analysis_events,
    load_recent_news_events,
)


def _setup_async_session(tmp_path: Path):
    db_path = tmp_path / "analysis-repository.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


def test_load_recent_news_events_dedupes_archived_batches(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        id="stock-archive-v1",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="旧批次",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock-archive",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=datetime(2026, 3, 20, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="stock-archive-v2",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="新批次",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/stock-archive",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=datetime(2026, 3, 21, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="policy-single",
                        scope="policy",
                        cache_variant="policy_source",
                        ts_code=None,
                        symbol=None,
                        title="白酒行业监管新规",
                        summary="政策摘要",
                        published_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
                        url="https://example.com/policy-single",
                        publisher="政策源",
                        source="policy_gateway",
                        macro_topic="regulation_policy",
                        fetched_at=datetime(2026, 3, 22, 10, 5, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

            rows = await load_recent_news_events(
                session,
                "600519.SH",
                topic=None,
                anchor_event_id=None,
                published_from=None,
                published_to=None,
                limit=10,
            )

            assert len(rows) == 2
            assert rows[0].title == "白酒行业监管新规"
            assert rows[1].summary == "新批次"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_recent_news_events_keeps_anchor_event_first(tmp_path: Path) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    NewsEvent(
                        id="anchor-old",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="旧批次锚点",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/anchor",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key="stock-cluster-1",
                        fetched_at=datetime(2026, 3, 20, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="anchor-new",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title="贵州茅台业绩增长超预期",
                        summary="新批次锚点",
                        published_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                        url="https://example.com/anchor",
                        publisher="测试源",
                        source="eastmoney_stock",
                        cluster_key="stock-cluster-1",
                        fetched_at=datetime(2026, 3, 21, 9, 5, tzinfo=UTC),
                    ),
                    NewsEvent(
                        id="policy-latest",
                        scope="policy",
                        cache_variant="policy_source",
                        ts_code=None,
                        symbol=None,
                        title="白酒行业监管新规",
                        summary="政策摘要",
                        published_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
                        url="https://example.com/policy-single",
                        publisher="政策源",
                        source="policy_gateway",
                        macro_topic="regulation_policy",
                        fetched_at=datetime(2026, 3, 22, 10, 5, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

            rows = await load_recent_news_events(
                session,
                "600519.SH",
                topic=None,
                anchor_event_id="anchor-old",
                published_from=None,
                published_to=None,
                limit=10,
            )

            assert len(rows) == 2
            assert rows[0].id == "anchor-old"
            assert rows[1].id == "policy-latest"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_recent_news_events_candidate_limit_returns_larger_candidate_pool(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
            session.add_all(
                [
                    NewsEvent(
                        id=f"stock-{index}",
                        scope="stock",
                        cache_variant="with_announcements",
                        ts_code="600519.SH",
                        symbol="600519",
                        title=f"个股事件 {index}",
                        summary="候选池事件",
                        published_at=base_time - timedelta(minutes=index),
                        url=f"https://example.com/stock-{index}",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=base_time - timedelta(minutes=index),
                    )
                    for index in range(4)
                ]
            )
            await session.commit()

            rows = await load_recent_news_events(
                session,
                "600519.SH",
                topic=None,
                anchor_event_id=None,
                published_from=None,
                published_to=None,
                limit=1,
                candidate_limit=3,
            )

            assert len(rows) == 3

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_recent_news_events_includes_hot_context_when_topic_missing(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            base_time = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
            session.add_all(
                [
                    NewsEvent(
                        id='stock-1',
                        scope='stock',
                        cache_variant='with_announcements',
                        ts_code='000001.SZ',
                        symbol='000001',
                        title='个股事件',
                        summary='个股摘要',
                        published_at=base_time - timedelta(minutes=3),
                        url='https://example.com/stock-1',
                        publisher='测试源',
                        source='eastmoney_stock',
                        fetched_at=base_time - timedelta(minutes=3),
                    ),
                    NewsEvent(
                        id='policy-1',
                        scope='policy',
                        cache_variant='policy_source',
                        ts_code=None,
                        symbol=None,
                        title='政策事件',
                        summary='政策摘要',
                        published_at=base_time - timedelta(minutes=2),
                        url='https://example.com/policy-1',
                        publisher='政策源',
                        source='miit',
                        macro_topic='industrial_policy',
                        fetched_at=base_time - timedelta(minutes=2),
                    ),
                    NewsEvent(
                        id='hot-1',
                        scope='hot',
                        cache_variant='global',
                        ts_code=None,
                        symbol=None,
                        title='热点事件',
                        summary='热点摘要',
                        published_at=base_time - timedelta(minutes=1),
                        url='https://example.com/hot-1',
                        publisher='热点源',
                        source='eastmoney_global',
                        macro_topic='commodity_supply',
                        fetched_at=base_time,
                    ),
                ]
            )
            await session.commit()

            rows = await load_recent_news_events(
                session,
                '000001.SZ',
                topic=None,
                anchor_event_id=None,
                published_from=None,
                published_to=None,
                limit=10,
            )

            assert {row.scope for row in rows} == {'stock', 'policy', 'hot'}

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_load_analysis_events_candidate_limit_supports_summary_oversampling(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
            session.add_all(
                [
                    NewsEvent(
                        id=f"event-{index}",
                        scope="stock",
                        cache_variant="default",
                        ts_code="600519.SH",
                        symbol="600519",
                        title=f"摘要事件 {index}",
                        summary="摘要候选",
                        published_at=base_time - timedelta(minutes=index),
                        url=f"https://example.com/summary-{index}",
                        publisher="测试源",
                        source="eastmoney_stock",
                        fetched_at=base_time - timedelta(minutes=index),
                    )
                    for index in range(4)
                ]
            )
            session.add_all(
                [
                    AnalysisEventLink(
                        event_id=f"event-{index}",
                        ts_code="600519.SH",
                        created_at=base_time - timedelta(minutes=index),
                    )
                    for index in range(4)
                ]
            )
            await session.commit()

            rows = await load_analysis_events(
                session,
                "600519.SH",
                limit=1,
                candidate_limit=3,
            )

            assert len(rows) == 3
            assert rows[0]["event_id"] == "event-0"

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_list_analysis_agent_runs_for_reports_groups_rows_by_report_id(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            session.add_all(
                [
                    AnalysisReport(
                        id="report-1",
                        ts_code="600519.SH",
                        status="ready",
                        summary="报告 1",
                        risk_points=[],
                        factor_breakdown=[],
                        generated_at=datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
                    ),
                    AnalysisReport(
                        id="report-2",
                        ts_code="600519.SH",
                        status="ready",
                        summary="报告 2",
                        risk_points=[],
                        factor_breakdown=[],
                        generated_at=datetime(2026, 3, 25, 11, 0, tzinfo=UTC),
                    ),
                ]
            )
            session.add_all(
                [
                    AnalysisAgentRun(
                        session_id="session-1",
                        report_id="report-1",
                        role_key="planner",
                        role_label="研究规划",
                        status="completed",
                        sort_order=1,
                    ),
                    AnalysisAgentRun(
                        session_id="session-1",
                        report_id="report-1",
                        role_key="decision",
                        role_label="最终裁决",
                        status="completed",
                        sort_order=6,
                    ),
                    AnalysisAgentRun(
                        session_id="session-2",
                        report_id="report-2",
                        role_key="audit",
                        role_label="证据审计",
                        status="completed",
                        sort_order=3,
                    ),
                ]
            )
            await session.commit()

            grouped = await list_analysis_agent_runs_for_reports(
                session,
                ["report-1", "report-2"],
            )

        assert [row.role_key for row in grouped["report-1"]] == [
            "planner",
            "decision",
        ]
        assert [row.role_key for row in grouped["report-2"]] == ["audit"]

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_claim_next_analysis_session_for_worker_allows_only_one_concurrent_winner() -> None:
    class _FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _AsyncBarrier:
        def __init__(self, parties: int) -> None:
            self._parties = parties
            self._count = 0
            self._event = asyncio.Event()
            self._guard = asyncio.Lock()

        async def wait(self) -> None:
            async with self._guard:
                self._count += 1
                if self._count >= self._parties:
                    self._event.set()
            await self._event.wait()

    class _FakeConcurrentClaimSession:
        def __init__(self, shared_state: dict[str, object], barrier: _AsyncBarrier) -> None:
            self._shared_state = shared_state
            self._barrier = barrier

        async def execute(self, statement):
            statement_kind = getattr(statement, "__visit_name__", "")
            if statement_kind == "update":
                if self._shared_state["available"]:
                    self._shared_state["available"] = False
                    return _FakeResult("session-queued-1")
                return _FakeResult(None)

            if statement_kind == "select":
                await self._barrier.wait()
                if self._shared_state["available"]:
                    return _FakeResult(
                        SimpleNamespace(
                            id="session-queued-1",
                            status="queued",
                            started_at=None,
                            completed_at=None,
                            error_message=None,
                        )
                    )
                return _FakeResult(None)

            raise AssertionError(f"unexpected statement kind: {statement_kind}")

        async def flush(self) -> None:
            self._shared_state["available"] = False

    async def run_test() -> None:
        shared_state = {"available": True}
        barrier = _AsyncBarrier(parties=2)
        sessions = [
            _FakeConcurrentClaimSession(shared_state, barrier),
            _FakeConcurrentClaimSession(shared_state, barrier),
        ]

        results = await asyncio.gather(
            claim_next_analysis_session_for_worker(
                sessions[0],
                stale_before=datetime.now(UTC) - timedelta(seconds=900),
            ),
            claim_next_analysis_session_for_worker(
                sessions[1],
                stale_before=datetime.now(UTC) - timedelta(seconds=900),
            ),
        )

        # 并发认领时只能有一个 worker 成功，另一个必须拿到空结果。
        assert results.count("session-queued-1") == 1
        assert results.count(None) == 1

    asyncio.run(run_test())


def test_claim_next_analysis_session_for_worker_uses_heartbeat_for_stale_running(
    tmp_path: Path,
) -> None:
    engine, session_maker = _setup_async_session(tmp_path)

    async def run_test() -> None:
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=900)
        async with session_maker() as session:
            fresh_running = AnalysisGenerationSession(
                id="session-running-fresh",
                analysis_key="600519.SH|||0|manual|functional_multi_agent",
                ts_code="600519.SH",
                status="running",
                trigger_source="manual",
                trigger_source_group="manual",
                use_web_search=False,
                analysis_mode="functional_multi_agent",
                started_at=now - timedelta(minutes=40),
                updated_at=now - timedelta(minutes=40),
                heartbeat_at=now,
            )
            expired_running = AnalysisGenerationSession(
                id="session-running-expired",
                analysis_key="000001.SZ|||0|manual|functional_multi_agent",
                ts_code="000001.SZ",
                status="running",
                trigger_source="manual",
                trigger_source_group="manual",
                use_web_search=False,
                analysis_mode="functional_multi_agent",
                started_at=now - timedelta(minutes=40),
                updated_at=now - timedelta(minutes=40),
                heartbeat_at=now - timedelta(minutes=40),
            )
            session.add_all([fresh_running, expired_running])
            await session.commit()

        async with session_maker() as session:
            claimed_id = await claim_next_analysis_session_for_worker(
                session,
                stale_before=stale_before,
            )
            await session.commit()

        assert claimed_id == "session-running-expired"

        async with session_maker() as session:
            fresh_after = await session.get(
                AnalysisGenerationSession,
                "session-running-fresh",
            )
            expired_after = await session.get(
                AnalysisGenerationSession,
                "session-running-expired",
            )

        assert fresh_after is not None
        assert fresh_after.status == "running"
        assert fresh_after.heartbeat_at == now.replace(tzinfo=None)
        assert expired_after is not None
        assert expired_after.heartbeat_at is not None
        assert expired_after.heartbeat_at > stale_before.replace(tzinfo=None)

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
