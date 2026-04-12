from __future__ import annotations

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

    sections.extend(
        [
            "",
            "## 摘要",
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

    sections.extend(["", "## 结构化来源"])
    structured_sources = report.structured_sources or []
    if structured_sources:
        for item in structured_sources:
            sections.append(
                f"- {item.get('provider') or 'unknown'}：{item.get('count') or 0}"
            )
    else:
        sections.append("- 暂无结构化来源")

    sections.extend(["", "## Web 来源"])
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
