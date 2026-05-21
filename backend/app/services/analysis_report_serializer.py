from __future__ import annotations

from app.schemas.analysis import (
    AnalysisReportArchiveItemResponse,
    AnalysisReportResponse,
)
from app.services.analysis_source_service import build_source_items


def serialize_report(
    report_obj: object | None,
    *,
    evidence_payloads: list[dict[str, object]] | None = None,
    pipeline_roles: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    if report_obj is None:
        return None

    raw_structured_sources = getattr(report_obj, "structured_sources", None) or []
    raw_web_sources = getattr(report_obj, "web_sources", None) or []
    raw_source_items = getattr(report_obj, "source_items", None) or []
    resolved_source_items = (
        raw_source_items
        if raw_source_items
        else build_source_items(
            events=evidence_payloads or [],
            structured_sources=raw_structured_sources,
            web_sources=raw_web_sources,
        )
    )
    report = AnalysisReportResponse.model_validate(
        {
            "id": getattr(report_obj, "id", None),
            "status": getattr(report_obj, "status", "pending") or "pending",
            "summary": getattr(report_obj, "summary", ""),
            "risk_points": getattr(report_obj, "risk_points", None) or [],
            "factor_breakdown": getattr(report_obj, "factor_breakdown", None) or [],
            "generated_at": getattr(report_obj, "generated_at", None),
            "topic": getattr(report_obj, "topic", None),
            "published_from": getattr(report_obj, "published_from", None),
            "published_to": getattr(report_obj, "published_to", None),
            "trigger_source": getattr(report_obj, "trigger_source", "manual"),
            "anchor_event_id": getattr(report_obj, "anchor_event_id", None),
            "anchor_event_title": getattr(report_obj, "anchor_event_title", None),
            "used_web_search": getattr(report_obj, "used_web_search", False),
            "web_search_status": getattr(report_obj, "web_search_status", "disabled"),
            "session_id": getattr(report_obj, "session_id", None),
            "started_at": getattr(report_obj, "started_at", None),
            "completed_at": getattr(report_obj, "completed_at", None),
            "content_format": getattr(report_obj, "content_format", "markdown"),
            "analysis_mode": getattr(report_obj, "analysis_mode", "single"),
            "orchestrator_version": getattr(report_obj, "orchestrator_version", None),
            "selected_hypothesis": getattr(report_obj, "selected_hypothesis", None),
            "decision_confidence": getattr(report_obj, "decision_confidence", None),
            "decision_reason_summary": getattr(
                report_obj,
                "decision_reason_summary",
                None,
            ),
            "research_plan": getattr(report_obj, "research_plan", None),
            "structured_sources": raw_structured_sources,
            "evidence_event_count": (
                int(getattr(report_obj, "evidence_event_count"))
                if getattr(report_obj, "evidence_event_count", None) is not None
                else len(evidence_payloads or [])
            ),
            "evidence_events": evidence_payloads or [],
            "web_sources": raw_web_sources,
            "source_items": resolved_source_items,
            "pipeline_roles": pipeline_roles or [],
            "prompt_version": getattr(report_obj, "prompt_version", None),
            "model_name": getattr(report_obj, "model_name", None),
            "reasoning_effort": getattr(report_obj, "reasoning_effort", None),
            "token_usage_input": getattr(report_obj, "token_usage_input", None),
            "token_usage_output": getattr(report_obj, "token_usage_output", None),
            "cost_estimate": (
                float(getattr(report_obj, "cost_estimate"))
                if getattr(report_obj, "cost_estimate", None) is not None
                else None
            ),
            "failure_type": getattr(report_obj, "failure_type", None),
        }
    )
    return report.model_dump()


def serialize_report_archive_item(
    report_obj: object,
    *,
    evidence_payloads: list[dict[str, object]] | None = None,
    pipeline_roles: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return AnalysisReportArchiveItemResponse.model_validate(
        serialize_report(
            report_obj,
            evidence_payloads=evidence_payloads,
            pipeline_roles=pipeline_roles,
        )
    ).model_dump()
