import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.news_event import NewsEvent
from app.models.policy_document import PolicyDocument
from app.services.policy_projection_service import project_policy_documents_to_news_events


def test_policy_documents_project_to_news_events_for_policy_scope(tmp_path) -> None:
    db_file = tmp_path / "policy-projection.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "policy-projection.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            document = PolicyDocument(
                id="policy-doc-1",
                source="gov_cn",
                source_document_id="gov-001",
                url_hash="hash-001",
                title="国务院关于支持科技创新的若干政策措施",
                summary="支持科技创新和设备更新。",
                document_no="国发〔2026〕1号",
                issuing_authority="国务院",
                policy_level="state_council",
                category="industry",
                macro_topic="industrial_policy",
                industry_tags_json=["ai_computing"],
                market_tags_json=["a_share"],
                published_at=datetime(2026, 3, 31, 1, 0, tzinfo=UTC),
                url="https://www.gov.cn/zhengce/content/2026-03/31/content_000002.htm",
                content_text="为支持科技创新，现提出若干政策措施。",
                raw_payload_json={"id": "gov-001"},
                metadata_status="ready",
                projection_status="pending",
            )
            session.add(document)
            await session.commit()

        async with session_maker() as session:
            document = await session.get(PolicyDocument, "policy-doc-1")
            await project_policy_documents_to_news_events(
                session,
                documents=[document],
                fetched_at=datetime(2026, 3, 31, 10, 0, tzinfo=UTC),
                batch_id="policy-batch-1",
            )
            await session.commit()

            projected_count = await session.scalar(
                select(func.count()).select_from(NewsEvent)
            )
            projected_row = (
                await session.execute(select(NewsEvent).limit(1))
            ).scalar_one()

            # 关键断言：政策主表是主数据，news_events 只保留兼容投影。
            assert projected_count == 1
            assert projected_row.scope == "policy"
            assert projected_row.external_id == "policy_document:policy-doc-1"
            assert projected_row.source == "gov_cn"
            assert projected_row.publisher == "国务院"
            assert projected_row.evidence_kind == "policy_document"


    asyncio.run(run_test())
