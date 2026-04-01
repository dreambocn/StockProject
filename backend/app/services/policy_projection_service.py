from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_event import NewsEvent
from app.models.policy_document import PolicyDocument
from app.services.news_mapper_service import (
    build_cluster_key,
    map_policy_document_to_news_event_response,
)


POLICY_DOCUMENT_PROVIDER = "policy_document"


def build_policy_document_external_id(document_id: str) -> str:
    return f"policy_document:{document_id}"


def _normalize_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _build_projection_summary(document: PolicyDocument) -> str | None:
    if document.summary:
        return document.summary
    if document.content_text:
        return document.content_text[:180]
    return None


async def project_policy_documents_to_news_events(
    session: AsyncSession,
    *,
    documents: list[PolicyDocument],
    fetched_at: datetime,
    batch_id: str | None,
) -> list[NewsEvent]:
    projected_rows: list[NewsEvent] = []
    normalized_fetched_at = _normalize_datetime(fetched_at)

    for document in documents:
        external_id = build_policy_document_external_id(document.id)
        row = (
            await session.execute(
                select(NewsEvent).where(
                    NewsEvent.scope == "policy",
                    NewsEvent.external_id == external_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = NewsEvent(
                scope="policy",
                cache_variant="policy_source",
                title=document.title,
                source=document.source,
                provider=POLICY_DOCUMENT_PROVIDER,
                external_id=external_id,
                fetched_at=normalized_fetched_at,
            )
            session.add(row)

        projection = map_policy_document_to_news_event_response(
            document,
            fetched_at=normalized_fetched_at,
        )
        row.cache_variant = projection.cache_variant
        row.title = projection.title
        row.summary = _build_projection_summary(document)
        row.published_at = projection.published_at
        row.url = projection.url
        row.publisher = projection.publisher
        row.source = projection.source
        row.provider = POLICY_DOCUMENT_PROVIDER
        row.cluster_key = build_cluster_key(
            title=document.title,
            published_at=document.published_at,
            macro_topic=document.macro_topic,
        )
        row.batch_id = batch_id
        row.source_priority = 40
        row.evidence_kind = "policy_document"
        row.macro_topic = document.macro_topic or "other"
        row.event_type = "policy"
        row.fetched_at = normalized_fetched_at
        # 关键流程：投影成功后回写主表状态，避免后台误判为“尚未兼容到新闻链路”。
        document.projection_status = "projected"
        projected_rows.append(row)

    await session.flush()
    return projected_rows
