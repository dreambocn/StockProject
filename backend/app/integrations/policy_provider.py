from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class PolicyDocumentSeed:
    source: str
    source_document_id: str | None
    title: str
    summary: str | None
    document_no: str | None
    issuing_authority: str | None
    policy_level: str | None
    category: str | None
    published_at: datetime | None
    effective_at: datetime | None
    url: str
    attachment_urls: list[str]
    content_text: str | None
    content_html: str | None
    raw_payload: dict[str, object]


@runtime_checkable
class PolicyProvider(Protocol):
    async def fetch_documents(self, *, now: datetime) -> list[PolicyDocumentSeed]:
        ...
