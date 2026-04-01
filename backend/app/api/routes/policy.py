from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.policy_document import PolicyDocument
from app.models.policy_document_attachment import PolicyDocumentAttachment
from app.schemas.policy import (
    PolicyDocumentAttachmentResponse,
    PolicyDocumentDetailResponse,
    PolicyDocumentListItemResponse,
    PolicyDocumentPageResponse,
    PolicyFilterResponse,
    PolicyFilterValueResponse,
)


router = APIRouter(prefix="/policy", tags=["policy"])


def _serialize_policy_document_item(
    document: PolicyDocument,
) -> PolicyDocumentListItemResponse:
    return PolicyDocumentListItemResponse(
        id=document.id,
        source=document.source,
        title=document.title,
        summary=document.summary,
        document_no=document.document_no,
        issuing_authority=document.issuing_authority,
        policy_level=document.policy_level,
        category=document.category,
        macro_topic=document.macro_topic,
        published_at=document.published_at,
        effective_at=document.effective_at,
        url=document.url,
        metadata_status=document.metadata_status,
        projection_status=document.projection_status,
    )


@router.get("/documents", response_model=PolicyDocumentPageResponse)
async def list_policy_documents(
    authority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    macro_topic: str | None = Query(default=None),
    published_from: str | None = Query(default=None),
    published_to: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> PolicyDocumentPageResponse:
    statement = select(PolicyDocument)

    normalized_authority = authority.strip() if authority else ""
    if normalized_authority:
        statement = statement.where(PolicyDocument.issuing_authority == normalized_authority)

    normalized_category = category.strip() if category else ""
    if normalized_category:
        statement = statement.where(PolicyDocument.category == normalized_category)

    normalized_macro_topic = macro_topic.strip() if macro_topic else ""
    if normalized_macro_topic:
        statement = statement.where(PolicyDocument.macro_topic == normalized_macro_topic)

    if keyword and keyword.strip():
        wildcard = f"%{keyword.strip()}%"
        # 关键流程：关键词同时覆盖标题、摘要、文号和正文，方便直接从政策中心检索。
        statement = statement.where(
            PolicyDocument.title.ilike(wildcard)
            | PolicyDocument.summary.ilike(wildcard)
            | PolicyDocument.document_no.ilike(wildcard)
            | PolicyDocument.content_text.ilike(wildcard)
        )

    if published_from:
        statement = statement.where(PolicyDocument.published_at >= published_from)
    if published_to:
        statement = statement.where(PolicyDocument.published_at <= published_to)

    total = int(
        (
            await session.execute(
                select(func.count()).select_from(statement.subquery())
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            statement
            .order_by(PolicyDocument.published_at.desc(), PolicyDocument.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return PolicyDocumentPageResponse(
        items=[_serialize_policy_document_item(item) for item in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=PolicyDocumentDetailResponse)
async def get_policy_document_detail(
    document_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PolicyDocumentDetailResponse:
    document = await session.get(PolicyDocument, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="policy document not found",
        )

    attachments = (
        await session.execute(
            select(PolicyDocumentAttachment)
            .where(PolicyDocumentAttachment.document_id == document_id)
            .order_by(PolicyDocumentAttachment.created_at.asc())
        )
    ).scalars().all()
    return PolicyDocumentDetailResponse(
        **_serialize_policy_document_item(document).model_dump(),
        content_text=document.content_text,
        content_html=document.content_html,
        attachments=[
            PolicyDocumentAttachmentResponse(
                attachment_url=item.attachment_url,
                attachment_name=item.attachment_name,
                attachment_type=item.attachment_type,
            )
            for item in attachments
        ],
        industry_tags=list(document.industry_tags_json or []),
        market_tags=list(document.market_tags_json or []),
    )


@router.get("/filters", response_model=PolicyFilterResponse)
async def get_policy_filters(
    session: AsyncSession = Depends(get_db_session),
) -> PolicyFilterResponse:
    async def load_distinct_values(column) -> list[str]:
        rows = (
            await session.execute(
                select(column)
                .where(column.is_not(None))
                .distinct()
                .order_by(column.asc())
            )
        ).scalars().all()
        return [str(item) for item in rows if str(item).strip()]

    authorities = await load_distinct_values(PolicyDocument.issuing_authority)
    categories = await load_distinct_values(PolicyDocument.category)
    macro_topics = await load_distinct_values(PolicyDocument.macro_topic)

    return PolicyFilterResponse(
        authorities=[
            PolicyFilterValueResponse(label=item, value=item) for item in authorities
        ],
        categories=[
            PolicyFilterValueResponse(label=item, value=item) for item in categories
        ],
        macro_topics=[
            PolicyFilterValueResponse(label=item, value=item) for item in macro_topics
        ],
    )
