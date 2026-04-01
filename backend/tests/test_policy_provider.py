import asyncio
from datetime import UTC, datetime

from app.integrations.policy_provider import (
    PolicyDocumentSeed,
    PolicyProvider,
)


class _FakePolicyProvider:
    async def fetch_documents(self, *, now: datetime) -> list[PolicyDocumentSeed]:
        return [
            PolicyDocumentSeed(
                source="gov_cn",
                source_document_id="gov-001",
                title="关于推动科技创新的政策文件",
                summary="政策摘要",
                document_no="国发〔2026〕1号",
                issuing_authority="国务院",
                policy_level="state_council",
                category="innovation",
                published_at=now,
                effective_at=None,
                url="https://example.com/policy",
                attachment_urls=["https://example.com/policy.pdf"],
                content_text="正文",
                content_html="<p>正文</p>",
                raw_payload={"title": "关于推动科技创新的政策文件"},
            )
        ]


def test_policy_provider_protocol_and_seed_shape() -> None:
    provider = _FakePolicyProvider()

    assert isinstance(provider, PolicyProvider)

    documents = asyncio.run(
        provider.fetch_documents(
            now=datetime(2026, 3, 31, 10, 0, tzinfo=UTC)
        )
    )

    assert documents[0].source == "gov_cn"
    assert documents[0].attachment_urls == ["https://example.com/policy.pdf"]
