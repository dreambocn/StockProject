from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from app.integrations.policy_provider import PolicyDocumentSeed


MACRO_TOPIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "monetary_policy",
        ("货币政策", "降准", "降息", "利率", "流动性", "逆回购", "再贷款", "人民银行", "央行"),
    ),
    (
        "capital_market_policy",
        ("资本市场", "证券", "上市公司", "信息披露", "并购重组", "交易所", "证监会", "基金"),
    ),
    (
        "fiscal_tax_policy",
        ("财政", "税", "减税", "退税", "专项债", "国债", "财政贴息"),
    ),
    (
        "energy_policy",
        ("能源", "电力", "煤炭", "石油", "天然气", "风电", "光伏", "储能"),
    ),
    (
        "industrial_policy",
        ("产业", "制造业", "人工智能", "算力", "半导体", "新能源汽车", "工业互联网", "科技创新"),
    ),
    (
        "regulation_policy",
        ("监管", "条例", "办法", "规则", "合规", "规范", "风险防控"),
    ),
)

SOURCE_DEFAULT_MACRO_TOPIC = {
    "pbc": "monetary_policy",
    "csrc": "capital_market_policy",
    "miit": "industrial_policy",
    "ndrc": "industrial_policy",
    "npc": "regulation_policy",
}

SOURCE_DEFAULT_POLICY_LEVEL = {
    "gov_cn": "state_council",
    "npc": "law",
    "pbc": "department",
    "csrc": "department",
    "ndrc": "department",
    "miit": "department",
}

SOURCE_DEFAULT_CATEGORY = {
    "pbc": "monetary",
    "csrc": "capital_market",
    "miit": "industry",
    "ndrc": "industry",
    "gov_cn": "general",
    "npc": "law",
}

INDUSTRY_TAG_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("banking", ("银行", "信贷", "再贷款")),
    ("brokerage", ("券商", "证券", "基金")),
    ("ai_computing", ("人工智能", "算力", "数据中心")),
    ("semiconductor", ("半导体", "芯片", "集成电路")),
    ("new_energy", ("新能源", "储能", "光伏", "风电", "动力电池")),
    ("automobile", ("汽车", "新能源汽车", "智能网联")),
    ("energy", ("能源", "电力", "煤炭", "石油", "天然气")),
)

MARKET_TAG_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("a_share", ("上市公司", "资本市场", "证券", "股市", "交易所")),
    ("bond", ("债券", "国债", "信用债", "融资成本")),
    ("commodity", ("原油", "黄金", "煤炭", "有色", "天然气")),
    ("fx", ("汇率", "外汇", "人民币汇率")),
)


@dataclass(slots=True, frozen=True)
class PolicyAttachmentNormalized:
    attachment_url: str
    attachment_name: str | None
    attachment_type: str | None
    attachment_hash: str


@dataclass(slots=True)
class PolicyDocumentNormalized:
    source: str
    source_document_id: str | None
    url_hash: str
    title: str
    summary: str | None
    document_no: str | None
    issuing_authority: str | None
    policy_level: str | None
    category: str | None
    macro_topic: str
    industry_tags: list[str] = field(default_factory=list)
    market_tags: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    effective_at: datetime | None = None
    expired_at: datetime | None = None
    url: str = ""
    content_text: str | None = None
    content_html: str | None = None
    raw_payload_json: dict[str, object] = field(default_factory=dict)
    metadata_status: str = "ready"
    projection_status: str = "pending"
    attachments: list[PolicyAttachmentNormalized] = field(default_factory=list)


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_url(url: str | None) -> str | None:
    text = _normalize_text(url)
    if text is None:
        return None
    parsed = urlsplit(text)
    normalized_path = parsed.path or "/"
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, parsed.query, ""))


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _normalize_document_no(document_no: str | None) -> str | None:
    text = _normalize_text(document_no)
    if text is None:
        return None
    return "".join(text.split())


def _build_haystack(seed: PolicyDocumentSeed) -> str:
    return " ".join(
        filter(
            None,
            [
                _normalize_text(seed.title),
                _normalize_text(seed.summary),
                _normalize_text(seed.document_no),
                _normalize_text(seed.issuing_authority),
                _normalize_text(seed.category),
                _normalize_text(seed.content_text),
            ],
        )
    ).lower()


def _detect_macro_topic(seed: PolicyDocumentSeed) -> str:
    category = _normalize_text(seed.category)
    normalized_category = category.lower() if category else ""
    if "monetary" in normalized_category:
        return "monetary_policy"
    if "capital" in normalized_category or "证券" in normalized_category:
        return "capital_market_policy"
    if "tax" in normalized_category or "fiscal" in normalized_category:
        return "fiscal_tax_policy"
    if "energy" in normalized_category or "能源" in normalized_category:
        return "energy_policy"
    if "industry" in normalized_category or "产业" in normalized_category:
        return "industrial_policy"

    haystack = _build_haystack(seed)
    for topic, keywords in MACRO_TOPIC_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return topic
    return SOURCE_DEFAULT_MACRO_TOPIC.get(seed.source, "other")


def _detect_policy_level(seed: PolicyDocumentSeed) -> str | None:
    explicit_level = _normalize_text(seed.policy_level)
    if explicit_level is not None:
        return explicit_level

    authority = _normalize_text(seed.issuing_authority) or ""
    if "国务院" in authority:
        return "state_council"
    if "全国人民代表大会" in authority or "法律法规" in authority:
        return "law"
    if authority:
        return "department"
    return SOURCE_DEFAULT_POLICY_LEVEL.get(seed.source)


def _detect_category(seed: PolicyDocumentSeed, *, macro_topic: str) -> str | None:
    explicit_category = _normalize_text(seed.category)
    if explicit_category is not None:
        return explicit_category.lower()
    if macro_topic == "monetary_policy":
        return "monetary"
    if macro_topic == "capital_market_policy":
        return "capital_market"
    if macro_topic == "fiscal_tax_policy":
        return "fiscal_tax"
    if macro_topic == "energy_policy":
        return "energy"
    if macro_topic == "industrial_policy":
        return "industry"
    if macro_topic == "regulation_policy":
        return "regulation"
    return SOURCE_DEFAULT_CATEGORY.get(seed.source)


def _collect_tags(
    haystack: str,
    rules: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[str]:
    tags: list[str] = []
    for tag, keywords in rules:
        if any(keyword.lower() in haystack for keyword in keywords):
            tags.append(tag)
    return tags


def _guess_attachment_type(attachment_url: str) -> str | None:
    suffix = PurePosixPath(urlsplit(attachment_url).path).suffix.lower().lstrip(".")
    return suffix or None


def _guess_attachment_name(attachment_url: str) -> str | None:
    name = PurePosixPath(urlsplit(attachment_url).path).name
    return name or None


def _normalize_attachments(
    attachment_urls: list[str],
) -> list[PolicyAttachmentNormalized]:
    attachments: list[PolicyAttachmentNormalized] = []
    seen_urls: set[str] = set()
    for attachment_url in attachment_urls:
        normalized_url = _normalize_url(attachment_url)
        if normalized_url is None or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        attachments.append(
            PolicyAttachmentNormalized(
                attachment_url=normalized_url,
                attachment_name=_guess_attachment_name(normalized_url),
                attachment_type=_guess_attachment_type(normalized_url),
                attachment_hash=_sha1_text(normalized_url),
            )
        )
    return attachments


def normalize_policy_seed(seed: PolicyDocumentSeed) -> PolicyDocumentNormalized:
    # 关键流程：归一化阶段统一补齐主题、类别、URL 哈希和附件元数据，
    # 让后续去重、入库和兼容投影都只消费稳定字段。
    title = _normalize_text(seed.title)
    normalized_url = _normalize_url(seed.url)
    if title is None:
        raise ValueError("政策标题不能为空")
    if normalized_url is None:
        raise ValueError("政策链接不能为空")

    normalized_document_no = _normalize_document_no(seed.document_no)
    macro_topic = _detect_macro_topic(seed)
    category = _detect_category(seed, macro_topic=macro_topic)
    haystack = _build_haystack(seed)
    attachments = _normalize_attachments(seed.attachment_urls)
    metadata_status = (
        "ready"
        if _normalize_text(seed.content_text)
        or _normalize_text(seed.content_html)
        or _normalize_text(seed.summary)
        else "partial"
    )

    return PolicyDocumentNormalized(
        source=seed.source,
        source_document_id=_normalize_text(seed.source_document_id),
        url_hash=_sha1_text(normalized_url),
        title=title,
        summary=_normalize_text(seed.summary),
        document_no=normalized_document_no,
        issuing_authority=_normalize_text(seed.issuing_authority),
        policy_level=_detect_policy_level(seed),
        category=category,
        macro_topic=macro_topic,
        industry_tags=_collect_tags(haystack, INDUSTRY_TAG_KEYWORDS),
        market_tags=_collect_tags(haystack, MARKET_TAG_KEYWORDS),
        published_at=_normalize_datetime(seed.published_at),
        effective_at=_normalize_datetime(seed.effective_at),
        expired_at=None,
        url=normalized_url,
        content_text=_normalize_text(seed.content_text),
        content_html=_normalize_text(seed.content_html),
        raw_payload_json=dict(seed.raw_payload),
        metadata_status=metadata_status,
        projection_status="pending",
        attachments=attachments,
    )
