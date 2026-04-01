from datetime import datetime

from pydantic import BaseModel


class PolicyDocumentAttachmentResponse(BaseModel):
    attachment_url: str
    attachment_name: str | None = None
    attachment_type: str | None = None


class PolicyDocumentListItemResponse(BaseModel):
    id: str
    source: str
    title: str
    summary: str | None = None
    document_no: str | None = None
    issuing_authority: str | None = None
    policy_level: str | None = None
    category: str | None = None
    macro_topic: str | None = None
    published_at: datetime | None = None
    effective_at: datetime | None = None
    url: str
    metadata_status: str
    projection_status: str


class PolicyDocumentDetailResponse(PolicyDocumentListItemResponse):
    content_text: str | None = None
    content_html: str | None = None
    attachments: list[PolicyDocumentAttachmentResponse] = []
    industry_tags: list[str] = []
    market_tags: list[str] = []


class PolicyDocumentPageResponse(BaseModel):
    items: list[PolicyDocumentListItemResponse]
    total: int
    page: int
    page_size: int


class PolicyFilterValueResponse(BaseModel):
    label: str
    value: str


class PolicyFilterResponse(BaseModel):
    authorities: list[PolicyFilterValueResponse]
    categories: list[PolicyFilterValueResponse]
    macro_topics: list[PolicyFilterValueResponse]


class PolicySyncRequest(BaseModel):
    force_refresh: bool = False


class AdminPolicySyncResponse(BaseModel):
    job_id: str | None = None
    job_type: str = "policy_sync"
    status: str
    provider_count: int
    raw_count: int
    normalized_count: int
    inserted_count: int
    updated_count: int
    deduped_count: int
    failed_provider_count: int
