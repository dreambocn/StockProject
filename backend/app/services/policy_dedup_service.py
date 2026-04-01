from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re

from app.services.policy_normalization_service import (
    PolicyAttachmentNormalized,
    PolicyDocumentNormalized,
)


@dataclass(slots=True)
class PolicyDedupResult:
    documents: list[PolicyDocumentNormalized]
    deduped_count: int


def _normalize_key_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"[\s\u3000]+", "", value).strip().lower()
    return text or None


def _build_dedup_keys(document: PolicyDocumentNormalized) -> list[str]:
    keys: list[str] = []
    normalized_document_no = _normalize_key_text(document.document_no)
    normalized_title = _normalize_key_text(document.title)
    normalized_source_document_id = _normalize_key_text(document.source_document_id)

    if normalized_document_no:
        keys.append(f"document_no:{normalized_document_no}")
    if normalized_title:
        keys.append(f"title:{normalized_title}")
    if normalized_source_document_id:
        keys.append(f"source:{document.source}:{normalized_source_document_id}")
    keys.append(f"url:{document.source}:{document.url_hash}")
    return keys


def _normalize_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _document_quality_score(document: PolicyDocumentNormalized) -> int:
    # 关键取舍：同一政策多源重复时优先保留正文更完整、附件更丰富的版本，
    # 避免把只有标题或短摘要的条目当成最终主数据。
    score = 0
    score += min(len(document.content_text or ""), 400)
    score += min(len(document.content_html or ""), 200) // 2
    score += min(len(document.summary or ""), 120) // 3
    score += len(document.attachments) * 20
    if document.published_at is not None:
        score += 10
    if document.metadata_status == "ready":
        score += 10
    return score


def _pick_richer_text(primary: str | None, secondary: str | None) -> str | None:
    candidates = [item for item in [primary, secondary] if item]
    if not candidates:
        return None
    return max(candidates, key=len)


def _merge_unique_tags(primary: list[str], secondary: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*primary, *secondary]:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_attachments(
    primary: list[PolicyAttachmentNormalized],
    secondary: list[PolicyAttachmentNormalized],
) -> list[PolicyAttachmentNormalized]:
    merged: list[PolicyAttachmentNormalized] = []
    seen_hashes: set[str] = set()
    for attachment in [*primary, *secondary]:
        if attachment.attachment_hash in seen_hashes:
            continue
        seen_hashes.add(attachment.attachment_hash)
        merged.append(attachment)
    return merged


def _merge_payloads(
    primary: dict[str, object],
    secondary: dict[str, object],
) -> dict[str, object]:
    merged = dict(secondary)
    merged.update(primary)
    return merged


def _choose_primary_document(
    left: PolicyDocumentNormalized,
    right: PolicyDocumentNormalized,
) -> tuple[PolicyDocumentNormalized, PolicyDocumentNormalized]:
    left_score = _document_quality_score(left)
    right_score = _document_quality_score(right)
    if right_score > left_score:
        return right, left
    if right_score < left_score:
        return left, right
    if _normalize_datetime(right.published_at) > _normalize_datetime(left.published_at):
        return right, left
    return left, right


def _merge_duplicate_documents(
    left: PolicyDocumentNormalized,
    right: PolicyDocumentNormalized,
) -> PolicyDocumentNormalized:
    primary, secondary = _choose_primary_document(left, right)
    return PolicyDocumentNormalized(
        source=primary.source,
        source_document_id=primary.source_document_id or secondary.source_document_id,
        url_hash=primary.url_hash,
        title=primary.title if len(primary.title) >= len(secondary.title) else secondary.title,
        summary=_pick_richer_text(primary.summary, secondary.summary),
        document_no=primary.document_no or secondary.document_no,
        issuing_authority=primary.issuing_authority or secondary.issuing_authority,
        policy_level=primary.policy_level or secondary.policy_level,
        category=primary.category or secondary.category,
        macro_topic=primary.macro_topic if primary.macro_topic != "other" else secondary.macro_topic,
        industry_tags=_merge_unique_tags(primary.industry_tags, secondary.industry_tags),
        market_tags=_merge_unique_tags(primary.market_tags, secondary.market_tags),
        published_at=primary.published_at or secondary.published_at,
        effective_at=primary.effective_at or secondary.effective_at,
        expired_at=primary.expired_at or secondary.expired_at,
        url=primary.url or secondary.url,
        content_text=_pick_richer_text(primary.content_text, secondary.content_text),
        content_html=_pick_richer_text(primary.content_html, secondary.content_html),
        raw_payload_json=_merge_payloads(primary.raw_payload_json, secondary.raw_payload_json),
        metadata_status=primary.metadata_status
        if primary.metadata_status == "ready"
        else secondary.metadata_status,
        projection_status=primary.projection_status,
        attachments=_merge_attachments(primary.attachments, secondary.attachments),
    )


def dedupe_policy_documents(
    documents: list[PolicyDocumentNormalized],
) -> PolicyDedupResult:
    deduped_documents: list[PolicyDocumentNormalized | None] = []
    key_to_index: dict[str, int] = {}
    deduped_count = 0

    for document in documents:
        keys = _build_dedup_keys(document)
        matched_indexes = sorted({key_to_index[key] for key in keys if key in key_to_index})
        if not matched_indexes:
            deduped_documents.append(document)
            new_index = len(deduped_documents) - 1
            for key in keys:
                key_to_index[key] = new_index
            continue

        target_index = matched_indexes[0]
        merged_document = deduped_documents[target_index]
        if merged_document is None:
            merged_document = document
        else:
            merged_document = _merge_duplicate_documents(merged_document, document)
        deduped_documents[target_index] = merged_document
        deduped_count += 1

        for extra_index in matched_indexes[1:]:
            extra_document = deduped_documents[extra_index]
            if extra_document is None:
                continue
            deduped_documents[target_index] = _merge_duplicate_documents(
                deduped_documents[target_index],
                extra_document,
            )
            deduped_documents[extra_index] = None

        for key in _build_dedup_keys(deduped_documents[target_index]):
            key_to_index[key] = target_index

    normalized_documents = [
        item for item in deduped_documents if item is not None
    ]
    normalized_documents.sort(
        key=lambda item: (
            _normalize_datetime(item.published_at),
            _document_quality_score(item),
        ),
        reverse=True,
    )
    return PolicyDedupResult(
        documents=normalized_documents,
        deduped_count=deduped_count,
    )
