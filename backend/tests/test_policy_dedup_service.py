from datetime import UTC, datetime

from app.services.policy_dedup_service import dedupe_policy_documents
from app.services.policy_normalization_service import (
    PolicyAttachmentNormalized,
    PolicyDocumentNormalized,
)


def test_dedup_policy_documents_prefers_official_text_over_short_summary() -> None:
    documents = [
        PolicyDocumentNormalized(
            source="gov_cn",
            source_document_id="gov-001",
            url_hash="hash-summary",
            title="国务院关于支持新能源产业发展的若干意见",
            summary="简短摘要",
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
            url="https://www.gov.cn/zhengce/summary.html",
            content_text=None,
            content_html=None,
            raw_payload_json={"version": "summary"},
            metadata_status="ready",
            projection_status="pending",
            attachments=[],
        ),
        PolicyDocumentNormalized(
            source="ndrc",
            source_document_id="ndrc-001",
            url_hash="hash-fulltext",
            title="国务院关于支持新能源产业发展的若干意见",
            summary="更完整的政策摘要，明确电网建设、储能示范和财政支持安排。",
            document_no="国发〔2026〕9号",
            issuing_authority="国务院",
            policy_level="state_council",
            category="industry",
            macro_topic="industrial_policy",
            industry_tags=["new_energy"],
            market_tags=["a_share", "bond"],
            published_at=datetime(2026, 3, 31, 1, 0, tzinfo=UTC),
            effective_at=None,
            expired_at=None,
            url="https://www.ndrc.gov.cn/xxgk/zcfb/tz/202603/t20260331_1234567.html",
            content_text="为推动新能源高质量发展，现就电网、储能、示范应用等事项通知如下。",
            content_html="<p>为推动新能源高质量发展。</p>",
            raw_payload_json={"version": "fulltext"},
            metadata_status="ready",
            projection_status="pending",
            attachments=[
                PolicyAttachmentNormalized(
                    attachment_url="https://www.ndrc.gov.cn/policy/fulltext.pdf",
                    attachment_name="正文附件.pdf",
                    attachment_type="pdf",
                    attachment_hash="att-001",
                )
            ],
        ),
    ]

    result = dedupe_policy_documents(documents)

    # 关键断言：多源重复时应保留正文更完整、附件更丰富的版本。
    assert result.deduped_count == 1
    assert len(result.documents) == 1
    assert result.documents[0].url == "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202603/t20260331_1234567.html"
    assert result.documents[0].content_text == "为推动新能源高质量发展，现就电网、储能、示范应用等事项通知如下。"
    assert result.documents[0].attachments[0].attachment_type == "pdf"
