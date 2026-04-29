import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.policy_document import PolicyDocument


def _create_context(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "policy-routes.db")
    init_sqlite_schema(engine)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return engine, session_maker, TestClient(app)


def _cleanup_context(engine) -> None:
    app.dependency_overrides.clear()


def test_policy_documents_route_supports_search_scope_and_pagination(tmp_path: Path) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    try:
        async def _seed() -> None:
            async with session_maker() as session:
                session.add_all(
                    [
                        PolicyDocument(
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
                            effective_at=None,
                            expired_at=None,
                            url="https://www.gov.cn/zhengce/content/2026-03/31/content_000002.htm",
                            content_text="为支持科技创新，现提出若干政策措施。",
                            content_html="<p>为支持科技创新，现提出若干政策措施。</p>",
                            raw_payload_json={"id": "gov-001"},
                            metadata_status="ready",
                            projection_status="projected",
                        ),
                        PolicyDocument(
                            id="policy-doc-2",
                            source="pbc",
                            source_document_id="pbc-001",
                            url_hash="hash-002",
                            title="中国人民银行召开货币政策委员会例会",
                            summary="保持流动性合理充裕。",
                            document_no="银发〔2026〕5号",
                            issuing_authority="中国人民银行",
                            policy_level="department",
                            category="monetary",
                            macro_topic="monetary_policy",
                            industry_tags_json=["banking"],
                            market_tags_json=["bond"],
                            published_at=datetime(2026, 3, 30, 1, 0, tzinfo=UTC),
                            effective_at=None,
                            expired_at=None,
                            url="https://www.pbc.gov.cn/zhengce/20260330/notice.html",
                            content_text="会议提出保持流动性合理充裕。",
                            content_html="<p>会议提出保持流动性合理充裕。</p>",
                            raw_payload_json={"id": "pbc-001"},
                            metadata_status="ready",
                            projection_status="pending",
                        ),
                        PolicyDocument(
                            id="policy-doc-3",
                            source="gov_cn",
                            source_document_id="gov-003",
                            url_hash="hash-003",
                            title="国务院关于设备更新的专项通知",
                            summary="聚焦重点行业设备升级。",
                            document_no="国发〔2026〕3号",
                            issuing_authority="国务院",
                            policy_level="state_council",
                            category="industry",
                            macro_topic="industrial_policy",
                            industry_tags_json=["advanced_manufacturing"],
                            market_tags_json=["a_share"],
                            published_at=datetime(2026, 3, 29, 1, 0, tzinfo=UTC),
                            effective_at=None,
                            expired_at=None,
                            url="https://www.gov.cn/zhengce/content/2026-03/29/content_000004.htm",
                            content_text="本通知明确提出加大科技创新专项资金支持力度。",
                            content_html="<p>本通知明确提出加大科技创新专项资金支持力度。</p>",
                            raw_payload_json={"id": "gov-003"},
                            metadata_status="ready",
                            projection_status="projected",
                        ),
                    ]
                )
                await session.commit()

        asyncio.run(_seed())

        basic_response = client.get(
            "/api/policy/documents?authority=%E5%9B%BD%E5%8A%A1%E9%99%A2&keyword=%E7%A7%91%E6%8A%80&search_scope=basic",
        )
        assert basic_response.status_code == 200
        basic_payload = basic_response.json()
        assert basic_payload["total"] == 1
        assert basic_payload["items"][0]["id"] == "policy-doc-1"

        fulltext_response = client.get(
            "/api/policy/documents?authority=%E5%9B%BD%E5%8A%A1%E9%99%A2&keyword=%E7%A7%91%E6%8A%80&search_scope=fulltext",
        )
        assert fulltext_response.status_code == 200
        fulltext_payload = fulltext_response.json()
        assert fulltext_payload["total"] == 2
        assert [item["id"] for item in fulltext_payload["items"]] == [
            "policy-doc-1",
            "policy-doc-3",
        ]

        pagination_response = client.get("/api/policy/documents?page=2&page_size=1")
        assert pagination_response.status_code == 200
        pagination_payload = pagination_response.json()
        assert pagination_payload["total"] == 3
        assert pagination_payload["page"] == 2
        assert pagination_payload["page_size"] == 1
        assert pagination_payload["items"][0]["id"] == "policy-doc-2"
    finally:
        client.close()
        _cleanup_context(engine)
