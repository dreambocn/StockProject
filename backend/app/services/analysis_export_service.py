from __future__ import annotations

import json
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_report import AnalysisReport
from app.services.analysis_repository import list_analysis_agent_runs_for_report


class AnalysisExportNotFoundError(Exception):
    pass


async def load_analysis_report_for_export(
    session: AsyncSession,
    *,
    report_id: str,
) -> AnalysisReport:
    report = await session.get(AnalysisReport, report_id)
    if report is None:
        raise AnalysisExportNotFoundError("analysis report not found")
    setattr(
        report,
        "pipeline_roles",
        await list_analysis_agent_runs_for_report(session, report.id),
    )
    return report


def render_report_markdown(report: AnalysisReport) -> str:
    sections: list[str] = []
    title_line = f"# {report.ts_code} 分析报告"
    sections.append(title_line)
    sections.append("")
    sections.append(f"- 生成时间：{report.generated_at.isoformat() if report.generated_at else '--'}")
    sections.append(f"- 触发来源：{report.trigger_source}")
    if getattr(report, "analysis_mode", "single") == "functional_multi_agent":
        sections.append("- 分析模式：纯职能多 Agent")
    if getattr(report, "selected_hypothesis", None):
        sections.append(f"- 采纳假设：{report.selected_hypothesis}")
    if getattr(report, "decision_confidence", None):
        sections.append(f"- 裁决置信度：{report.decision_confidence}")
    if getattr(report, "decision_reason_summary", None):
        sections.append(f"- 采纳理由：{report.decision_reason_summary}")
    if report.topic:
        sections.append(f"- 主题：{report.topic}")
    if report.anchor_event_title:
        sections.append(f"- 锚点事件：{report.anchor_event_title}")

    research_plan = getattr(report, "research_plan", None) or {}
    sections.extend(["", "## 研究计划"])
    if isinstance(research_plan, dict) and research_plan:
        plan_summary = str(research_plan.get("summary") or "").strip()
        if plan_summary:
            sections.append(plan_summary)
        questions = research_plan.get("priority_questions")
        if isinstance(questions, list) and questions:
            sections.append("")
            sections.append("### 优先问题")
            sections.extend([f"- {str(item)}" for item in questions if str(item).strip()])
        steps = research_plan.get("estimated_steps")
        if isinstance(steps, list) and steps:
            sections.append("")
            sections.append("### 预计步骤")
            sections.extend([f"- {str(item)}" for item in steps if str(item).strip()])
    else:
        sections.append("暂无独立研究计划记录")

    sections.extend(
        [
            "",
            "## 核心判断",
            report.summary or "暂无摘要",
            "",
            "## 风险提示",
        ]
    )
    risk_points = report.risk_points or []
    if risk_points:
        sections.extend([f"- {item}" for item in risk_points])
    else:
        sections.append("- 暂无明确风险提示")

    sections.extend(["", "## 因子拆解"])
    factor_breakdown = report.factor_breakdown or []
    if factor_breakdown:
        for item in factor_breakdown:
            label = str(item.get("factor_label") or item.get("factor_key") or "未命名因子")
            reason = str(item.get("reason") or "").strip()
            weight = item.get("weight")
            if isinstance(weight, (int, float)):
                sections.append(f"- {label}（权重 {weight:.2f}）：{reason or '暂无说明'}")
            else:
                sections.append(f"- {label}：{reason or '暂无说明'}")
    else:
        sections.append("- 暂无因子拆解")

    sections.extend(["", "## 关键证据"])
    evidence_events = getattr(report, "evidence_events", None) or []
    if evidence_events:
        for item in evidence_events:
            title = str(item.get("title") or item.get("event_id") or "未命名事件")
            source = str(item.get("source") or "未知来源")
            confidence = str(item.get("confidence") or "未知置信度")
            sections.append(f"- {title}｜{source}｜{confidence}")
    else:
        sections.append("- 暂无关键事件快照")

    sections.extend(["", "## 来源列表"])
    source_items = getattr(report, "source_items", None) or []
    if source_items:
        for item in source_items:
            title = str(item.get("title") or "未命名来源")
            source_kind = str(item.get("source_kind") or "unknown")
            source_name = str(item.get("source_name") or item.get("domain") or "未知来源")
            url = str(item.get("url") or "").strip()
            line = f"- {title}｜{source_kind}｜{source_name}"
            if url:
                line = f"{line}｜{url}"
            sections.append(line)

    sections.extend(["", "### 结构化来源"])
    structured_sources = report.structured_sources or []
    if structured_sources:
        for item in structured_sources:
            sections.append(
                f"- {item.get('provider') or 'unknown'}：{item.get('count') or 0}"
            )
    else:
        sections.append("- 暂无结构化来源")

    sections.extend(["", "### Web 来源"])
    web_sources = report.web_sources or []
    if web_sources:
        for item in web_sources:
            title = str(item.get("title") or item.get("url") or "未命名来源")
            source = str(item.get("source") or item.get("domain") or "未知来源")
            url = str(item.get("url") or "").strip()
            line = f"- {title}｜{source}"
            if url:
                line = f"{line}｜{url}"
            sections.append(line)
    else:
        sections.append("- 暂无 Web 来源")

    pipeline_roles = getattr(report, "pipeline_roles", None) or []
    if pipeline_roles:
        sections.extend(["", "## 研究流水线"])
        for item in pipeline_roles:
            sections.append(
                f"- {getattr(item, 'role_label', '角色')}（{getattr(item, 'status', 'unknown')}）："
                f"{getattr(item, 'summary', None) or '暂无摘要'}"
            )

    sections.extend(["", "## 运行元数据"])
    runtime_items = [
        f"分析模式：{getattr(report, 'analysis_mode', 'single')}",
        f"联网状态：{getattr(report, 'web_search_status', 'disabled')}",
        f"Prompt：{getattr(report, 'prompt_version', None) or '--'}",
        f"模型：{getattr(report, 'model_name', None) or '--'}",
    ]
    sections.extend([f"- {item}" for item in runtime_items])

    return "\n".join(sections).strip() + "\n"


def render_report_html(report: AnalysisReport) -> str:
    markdown = render_report_markdown(report)
    paragraphs = []
    for block in markdown.split("\n\n"):
        stripped = block.strip()
        if not stripped:
            continue
        lines = stripped.splitlines()
        first_line = lines[0]
        if first_line.startswith("# "):
            paragraphs.append(f"<h1>{escape(first_line[2:])}</h1>")
            continue
        if first_line.startswith("## "):
            paragraphs.append(f"<h2>{escape(first_line[3:])}</h2>")
            if len(lines) > 1:
                body = "".join(
                    f"<p>{escape(line)}</p>" if not line.startswith("- ") else f"<li>{escape(line[2:])}</li>"
                    for line in lines[1:]
                )
                if "<li>" in body:
                    body = f"<ul>{body}</ul>"
                paragraphs.append(body)
            continue

        if all(line.startswith("- ") for line in lines):
            paragraphs.append(
                "<ul>"
                + "".join(f"<li>{escape(line[2:])}</li>" for line in lines)
                + "</ul>"
            )
        else:
            paragraphs.append("".join(f"<p>{escape(line)}</p>" for line in lines))

    return (
        "<!DOCTYPE html>"
        "<html lang=\"zh-CN\">"
        "<head>"
        "<meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{escape(report.ts_code)} 分析报告</title>"
        "<style>"
        "body{font-family:'Microsoft YaHei','PingFang SC',sans-serif;padding:32px;margin:0;color:#1f2937;background:#fff;line-height:1.7;}"
        "main{max-width:900px;margin:0 auto;}"
        "h1,h2{color:#111827;}"
        "h1{margin-bottom:20px;}"
        "h2{margin-top:28px;margin-bottom:12px;border-bottom:1px solid #e5e7eb;padding-bottom:6px;}"
        "p,li{font-size:14px;}"
        "ul{padding-left:20px;}"
        "@media print{body{padding:0;} h2{break-after:avoid;}}"
        "</style>"
        "</head>"
        "<body><main>"
        + "".join(paragraphs)
        + "</main></body></html>"
    )


def build_source_manifest(report: AnalysisReport) -> dict[str, object]:
    source_items = getattr(report, "source_items", None) or []
    return {
        "report_id": report.id,
        "ts_code": report.ts_code,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "research_plan": getattr(report, "research_plan", None) or None,
        "source_items": source_items,
        "structured_sources": report.structured_sources or [],
        "web_sources": report.web_sources or [],
        "runtime": {
            "analysis_mode": getattr(report, "analysis_mode", "single"),
            "web_search_status": getattr(report, "web_search_status", "disabled"),
            "prompt_version": getattr(report, "prompt_version", None),
            "model_name": getattr(report, "model_name", None),
        },
    }


def render_report_package_html(report: AnalysisReport) -> str:
    manifest = json.dumps(build_source_manifest(report), ensure_ascii=False, indent=2)
    markdown = escape(render_report_markdown(report))
    return (
        "<!DOCTYPE html>"
        "<html lang=\"zh-CN\">"
        "<head><meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{escape(report.ts_code)} 研究包</title>"
        "<style>"
        "body{font-family:'Microsoft YaHei','PingFang SC',sans-serif;margin:0;padding:28px;background:#f8fafc;color:#111827;}"
        "main{max-width:1080px;margin:0 auto;display:grid;gap:20px;}"
        "section{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:18px;}"
        "pre{white-space:pre-wrap;word-break:break-word;background:#0f172a;color:#e5e7eb;padding:14px;border-radius:8px;overflow:auto;}"
        "h1,h2{margin-top:0;}"
        "</style></head>"
        "<body><main>"
        f"<h1>{escape(report.ts_code)} 研究包</h1>"
        "<section><h2>report.md</h2><pre>"
        f"{markdown}"
        "</pre></section>"
        "<section><h2>source_manifest.json</h2><pre>"
        f"{escape(manifest)}"
        "</pre></section>"
        "</main></body></html>"
    )
