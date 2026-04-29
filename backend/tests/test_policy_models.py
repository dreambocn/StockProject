import asyncio

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.models.policy_document import PolicyDocument


def test_policy_document_unique_by_source_and_url_hash(tmp_path) -> None:
    db_file = tmp_path / "policy-models.db"
    engine, session_maker = build_sqlite_test_context(tmp_path, "policy-models.db")

    async def run_test() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_maker() as session:
            session.add(
                PolicyDocument(
                    source="gov_cn",
                    source_document_id="doc-1",
                    url_hash="same-hash",
                    title="关于支持科技创新的若干政策措施",
                    url="https://example.com/policy-1",
                    metadata_status="ready",
                    projection_status="pending",
                )
            )
            await session.commit()

        async with session_maker() as session:
            session.add(
                PolicyDocument(
                    source="gov_cn",
                    source_document_id="doc-2",
                    url_hash="same-hash",
                    title="关于支持科技创新的若干政策措施（重复）",
                    url="https://example.com/policy-duplicate",
                    metadata_status="ready",
                    projection_status="pending",
                )
            )

            with pytest.raises(IntegrityError):
                await session.commit()


    asyncio.run(run_test())
