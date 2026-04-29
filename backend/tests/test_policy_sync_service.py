import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.integrations.policy_provider import PolicyDocumentSeed
from app.models.system_job_run import SystemJobRun
from app.services.policy_sync_service import sync_policy_documents


class _SuccessfulPolicyProvider:
    source = "gov_cn"

    async def fetch_documents(self, *, now: datetime) -> list[PolicyDocumentSeed]:
        return [
            PolicyDocumentSeed(
                source="gov_cn",
                source_document_id="gov-001",
                title="国务院关于支持新能源产业发展的若干意见",
                summary="简短摘要",
                document_no="国发〔2026〕9号",
                issuing_authority="国务院",
                policy_level="state_council",
                category="industry",
                published_at=now,
                effective_at=None,
                url="https://www.gov.cn/zhengce/summary.html",
                attachment_urls=[],
                content_text=None,
                content_html=None,
                raw_payload={"source": "summary"},
            ),
            PolicyDocumentSeed(
                source="gov_cn",
                source_document_id="gov-002",
                title="国务院关于支持新能源产业发展的若干意见",
                summary="更完整的政策摘要，明确电网建设、储能示范和财政支持安排。",
                document_no="国发〔2026〕9号",
                issuing_authority="国务院",
                policy_level="state_council",
                category="industry",
                published_at=now,
                effective_at=None,
                url="https://www.gov.cn/zhengce/content/2026-03/31/content_000001.htm",
                attachment_urls=["https://www.gov.cn/policy/fulltext.pdf"],
                content_text="为推动新能源高质量发展，现就电网、储能、示范应用等事项通知如下。",
                content_html="<p>为推动新能源高质量发展。</p>",
                raw_payload={"source": "fulltext"},
            ),
        ]


class _FailingPolicyProvider:
    source = "pbc"

    async def fetch_documents(self, *, now: datetime) -> list[PolicyDocumentSeed]:
        _ = now
        raise RuntimeError("upstream timeout")


def test_policy_sync_service_records_job_metrics(tmp_path) -> None:
    db_file = tmp_path / "policy-sync-service.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "policy-sync-service.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            result = await sync_policy_documents(
                session,
                trigger_source="test.policy.sync",
                force_refresh=True,
                providers=[_SuccessfulPolicyProvider(), _FailingPolicyProvider()],
                now=datetime(2026, 3, 31, 10, 0, tzinfo=UTC),
            )

            job = (
                await session.execute(select(SystemJobRun).limit(1))
            ).scalar_one()

            # 关键断言：同步任务必须把 provider 统计和去重结果沉淀到 system_job_runs。
            assert result["provider_count"] == 2
            assert result["raw_count"] == 2
            assert result["normalized_count"] == 2
            assert result["inserted_count"] == 1
            assert result["updated_count"] == 0
            assert result["deduped_count"] == 1
            assert result["failed_provider_count"] == 1
            assert result["successful_provider_count"] == 1
            assert result["successful_providers"] == ["gov_cn"]
            assert result["failed_providers"] == ["pbc"]
            assert job.job_type == "policy_sync"
            assert job.status == "partial"
            assert job.metrics_json["provider_count"] == 2
            assert job.metrics_json["inserted_count"] == 1
            assert job.metrics_json["deduped_count"] == 1
            assert job.metrics_json["successful_provider_count"] == 1
            assert job.metrics_json["successful_providers"] == ["gov_cn"]
            assert job.metrics_json["failed_providers"] == ["pbc"]
            assert job.metrics_json["provider_stats"] == [
                {
                    "provider": "gov_cn",
                    "status": "success",
                    "error_type": None,
                    "raw_count": 2,
                    "normalized_count": 2,
                },
                {
                    "provider": "pbc",
                    "status": "failed",
                    "error_type": "RuntimeError",
                    "raw_count": 0,
                    "normalized_count": 0,
                },
            ]


    asyncio.run(run_test())
