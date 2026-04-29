import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.policy_document import PolicyDocument
from app.models.policy_document_attachment import PolicyDocumentAttachment
from app.services.policy_normalization_service import (
    PolicyAttachmentNormalized,
    PolicyDocumentNormalized,
)
from app.services.policy_repository import upsert_policy_documents


def _build_policy_document(*, summary: str, content_text: str | None) -> PolicyDocumentNormalized:
    attachments = [
        PolicyAttachmentNormalized(
            attachment_url="https://www.gov.cn/policy/fulltext.pdf",
            attachment_name="fulltext.pdf",
            attachment_type="pdf",
            attachment_hash="att-001",
        )
    ]
    return PolicyDocumentNormalized(
        source="gov_cn",
        source_document_id="gov-001",
        url_hash="hash-001",
        title="国务院关于支持新能源产业发展的若干意见",
        summary=summary,
        document_no="国发〔2026〕9号",
        issuing_authority="国务院",
        policy_level="state_council",
        category="industry",
        macro_topic="industrial_policy",
        industry_tags=["new_energy"],
        market_tags=["a_share"],
        published_at=datetime(2026, 3, 31, 1, 0, tzinfo=UTC),
        effective_at=None,
        expired_at=None,
        url="https://www.gov.cn/zhengce/content/2026-03/31/content_000001.htm",
        content_text=content_text,
        content_html="<p>正文</p>" if content_text else None,
        raw_payload_json={"title": "国务院关于支持新能源产业发展的若干意见"},
        metadata_status="ready",
        projection_status="pending",
        attachments=attachments,
    )


def test_upsert_policy_documents_updates_existing_row_without_duplication(tmp_path) -> None:
    db_file = tmp_path / "policy-repository.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "policy-repository.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            created = await upsert_policy_documents(
                session,
                documents=[_build_policy_document(summary="首次摘要", content_text=None)],
                sync_job_id="job-1",
            )
            await session.commit()

            assert created.inserted_count == 1
            assert created.updated_count == 0

        async with session_maker() as session:
            updated = await upsert_policy_documents(
                session,
                documents=[
                    _build_policy_document(
                        summary="更新后摘要",
                        content_text="为推动新能源高质量发展，现就电网、储能、示范应用等事项通知如下。",
                    )
                ],
                sync_job_id="job-2",
            )
            await session.commit()

            assert updated.inserted_count == 0
            assert updated.updated_count == 1

            document_count = await session.scalar(
                select(func.count()).select_from(PolicyDocument)
            )
            attachment_count = await session.scalar(
                select(func.count()).select_from(PolicyDocumentAttachment)
            )
            stored = (
                await session.execute(select(PolicyDocument).limit(1))
            ).scalar_one()

            # 关键断言：同一政策再次写入时只能更新原记录，不能产生重复主表。
            assert document_count == 1
            assert attachment_count == 1
            assert stored.summary == "更新后摘要"
            assert stored.content_text == "为推动新能源高质量发展，现就电网、储能、示范应用等事项通知如下。"
            assert stored.sync_job_id == "job-2"


    asyncio.run(run_test())
