from datetime import UTC, datetime, timedelta, timezone

from app.integrations.policy_provider import PolicyDocumentSeed
from app.services.policy_normalization_service import normalize_policy_seed


def test_normalize_policy_document_assigns_macro_topic() -> None:
    seed = PolicyDocumentSeed(
        source="pbc",
        source_document_id="pbc-001",
        title="中国人民银行关于实施适度宽松货币政策支持科技创新的通知",
        summary="通过再贷款和流动性工具支持科技企业融资。",
        document_no="银发〔2026〕12号",
        issuing_authority="中国人民银行",
        policy_level=None,
        category=None,
        published_at=datetime(2026, 3, 31, 9, 30, tzinfo=timezone(timedelta(hours=8))),
        effective_at=None,
        url="https://www.pbc.gov.cn/zhengcehuobisi/125207/125227/543210/index.html",
        attachment_urls=[
            "https://www.pbc.gov.cn/zhengcehuobisi/125207/125227/543210/policy.pdf"
        ],
        content_text=(
            "为保持流动性合理充裕，发挥再贷款工具作用，支持科技创新和设备更新项目。"
        ),
        content_html="<p>为保持流动性合理充裕，发挥再贷款工具作用。</p>",
        raw_payload={"title": "中国人民银行关于实施适度宽松货币政策支持科技创新的通知"},
    )

    normalized = normalize_policy_seed(seed)

    # 关键断言：归一化后必须产出可复用的宏观主题和稳定入库字段。
    assert normalized.source == "pbc"
    assert normalized.macro_topic == "monetary_policy"
    assert normalized.policy_level == "department"
    assert normalized.category == "monetary"
    assert normalized.issuing_authority == "中国人民银行"
    assert normalized.url_hash
    assert normalized.published_at == datetime(2026, 3, 31, 1, 30, tzinfo=UTC)
    assert normalized.attachments[0].attachment_type == "pdf"

