import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.integrations.policy_provider import PolicyDocumentSeed
from app.models.policy_document import PolicyDocument
from app.models.system_job_run import SystemJobRun
from app.services.policy_sync_service import sync_policy_documents


class _SingleDocumentProvider:
    source = "gov_cn"

    async def fetch_documents(self, *, now) -> list[PolicyDocumentSeed]:
        return [
            PolicyDocumentSeed(
                source="gov_cn",
                source_document_id="gov-001",
                title="国务院关于支持科技创新的若干政策措施",
                summary="支持科技创新和设备更新。",
                document_no="国发〔2026〕1号",
                issuing_authority="国务院",
                policy_level="state_council",
                category="industry",
                published_at=now,
                effective_at=None,
                url="https://www.gov.cn/zhengce/content/2026-03/31/content_000002.htm",
                attachment_urls=[],
                content_text="为支持科技创新，现提出若干政策措施。",
                content_html="<p>为支持科技创新，现提出若干政策措施。</p>",
                raw_payload={"id": "gov-001"},
            )
        ]


def test_policy_sync_creates_system_job_and_links_document(tmp_path) -> None:
    db_file = tmp_path / "policy-sync-job.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            result = await sync_policy_documents(
                session,
                trigger_source="script.policy.sync",
                force_refresh=True,
                providers=[_SingleDocumentProvider()],
            )
            assert result["inserted_count"] == 1

            job = (
                await session.execute(select(SystemJobRun).limit(1))
            ).scalar_one()
            document = (
                await session.execute(select(PolicyDocument).limit(1))
            ).scalar_one()

            assert job.job_type == "policy_sync"
            assert job.status == "success"
            assert job.metrics_json["inserted_count"] == 1
            # 关键断言：主数据要能回溯到本次同步任务，便于后台排障和审计。
            assert document.sync_job_id == job.id

        await engine.dispose()

    asyncio.run(run_test())
