from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_document import PolicyDocument
from app.models.policy_document_attachment import PolicyDocumentAttachment
from app.services.policy_normalization_service import (
    PolicyAttachmentNormalized,
    PolicyDocumentNormalized,
)


@dataclass(slots=True)
class PolicyRepositoryUpsertResult:
    documents: list[PolicyDocument]
    inserted_count: int
    updated_count: int


async def _load_existing_policy_document(
    session: AsyncSession,
    *,
    document: PolicyDocumentNormalized,
) -> PolicyDocument | None:
    if document.source_document_id:
        row = (
            await session.execute(
                select(PolicyDocument).where(
                    PolicyDocument.source == document.source,
                    PolicyDocument.source_document_id == document.source_document_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row

    return (
        await session.execute(
            select(PolicyDocument).where(
                PolicyDocument.source == document.source,
                PolicyDocument.url_hash == document.url_hash,
            )
        )
    ).scalar_one_or_none()


def _apply_policy_document_payload(
    row: PolicyDocument,
    *,
    document: PolicyDocumentNormalized,
    sync_job_id: str | None,
) -> None:
    row.source = document.source
    row.source_document_id = document.source_document_id
    row.url_hash = document.url_hash
    row.title = document.title
    row.summary = document.summary
    row.document_no = document.document_no
    row.issuing_authority = document.issuing_authority
    row.policy_level = document.policy_level
    row.category = document.category
    row.macro_topic = document.macro_topic
    row.industry_tags_json = document.industry_tags
    row.market_tags_json = document.market_tags
    row.published_at = document.published_at
    row.effective_at = document.effective_at
    row.expired_at = document.expired_at
    row.url = document.url
    row.content_text = document.content_text
    row.content_html = document.content_html
    row.raw_payload_json = document.raw_payload_json
    row.metadata_status = document.metadata_status
    row.projection_status = document.projection_status
    row.sync_job_id = sync_job_id


async def _upsert_policy_attachments(
    session: AsyncSession,
    *,
    document_id: str,
    attachments: list[PolicyAttachmentNormalized],
) -> None:
    existing_rows = (
        await session.execute(
            select(PolicyDocumentAttachment).where(
                PolicyDocumentAttachment.document_id == document_id
            )
        )
    ).scalars().all()
    existing_by_hash: dict[str, PolicyDocumentAttachment] = {}
    for row in existing_rows:
        key = row.attachment_hash or row.attachment_url
        existing_by_hash[key] = row

    for attachment in attachments:
        lookup_key = attachment.attachment_hash or attachment.attachment_url
        row = existing_by_hash.get(lookup_key)
        if row is None:
            row = PolicyDocumentAttachment(document_id=document_id)
            session.add(row)
        row.attachment_url = attachment.attachment_url
        row.attachment_name = attachment.attachment_name
        row.attachment_type = attachment.attachment_type
        row.attachment_hash = attachment.attachment_hash


async def upsert_policy_documents(
    session: AsyncSession,
    *,
    documents: list[PolicyDocumentNormalized],
    sync_job_id: str | None = None,
) -> PolicyRepositoryUpsertResult:
    persisted_documents: list[PolicyDocument] = []
    inserted_count = 0
    updated_count = 0

    for document in documents:
        existing_row = await _load_existing_policy_document(
            session,
            document=document,
        )
        is_created = existing_row is None
        row = existing_row or PolicyDocument(
            source=document.source,
            url_hash=document.url_hash,
            title=document.title,
            url=document.url,
            metadata_status=document.metadata_status,
            projection_status=document.projection_status,
        )
        if is_created:
            session.add(row)

        # 关键流程：主表字段统一由归一化结果覆盖，避免不同 Provider 在仓储层重复做业务判断。
        _apply_policy_document_payload(
            row,
            document=document,
            sync_job_id=sync_job_id,
        )
        await session.flush()
        await _upsert_policy_attachments(
            session,
            document_id=row.id,
            attachments=document.attachments,
        )
        persisted_documents.append(row)
        if is_created:
            inserted_count += 1
        else:
            updated_count += 1

    await session.flush()
    return PolicyRepositoryUpsertResult(
        documents=persisted_documents,
        inserted_count=inserted_count,
        updated_count=updated_count,
    )
