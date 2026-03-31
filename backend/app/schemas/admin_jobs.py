from datetime import datetime

from pydantic import BaseModel


class AdminJobLinkedEntityResponse(BaseModel):
    entity_type: str | None = None
    entity_id: str | None = None


class AdminJobListItemResponse(BaseModel):
    id: str
    job_type: str
    status: str
    trigger_source: str
    resource_type: str | None = None
    resource_key: str | None = None
    summary: str | None = None
    linked_entity: AdminJobLinkedEntityResponse = AdminJobLinkedEntityResponse()
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime
    updated_at: datetime


class AdminJobPageResponse(BaseModel):
    items: list[AdminJobListItemResponse]
    total: int
    page: int
    page_size: int


class AdminJobFailureSummaryResponse(BaseModel):
    id: str
    job_type: str
    trigger_source: str
    resource_key: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    finished_at: datetime | None = None


class AdminJobSummaryResponse(BaseModel):
    total: int
    status_counts: dict[str, int]
    type_counts: dict[str, int]
    recent_failures: list[AdminJobFailureSummaryResponse]


class AdminJobDetailResponse(AdminJobListItemResponse):
    idempotency_key: str | None = None
    payload_json: dict[str, object] | list[object] | None = None
    metrics_json: dict[str, object] | list[object] | None = None
    error_type: str | None = None
    error_message: str | None = None
