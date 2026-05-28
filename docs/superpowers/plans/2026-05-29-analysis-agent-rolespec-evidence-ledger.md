# Analysis Agent RoleSpec, EvidenceLedger, Status Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前多 Agent 分析从硬编码流水线升级为可验证的 RoleSpec 编排、共享 EvidenceLedger 证据账本，以及更准确的联网/fallback/校验状态语义。

**Architecture:** 后端新增小型编排域模型：每个 Agent 由 RoleSpec 描述输入、prompt、Pydantic 输出 schema、fallback 和联网策略；证据检索角色集中生成 EvidenceLedger，后续角色只消费共享账本，必要时补搜；角色运行记录和报告序列化保留兼容字段，同时新增细粒度状态字段。前端 API shape 可兼容旧字段，优先展示新增状态。

**Tech Stack:** FastAPI backend, Python 3.14, SQLAlchemy async, Pydantic, Alembic, Vue 3 + TypeScript, Vitest, pytest, PowerShell.

---

## Scope

本计划只覆盖功能型多 Agent 分析 `functional_multi_agent`。旧 `single` 分析通道保持兼容，不重构。

本计划不改变刷新入口、报告列表选择规则、任务中心调度策略，也不引入外部搜索缓存服务。联网仍使用现有 `llm_client_service.generate_llm_result(... use_web_search=True)`。

## Target Behavior

1. 每个 LLM Agent 的输入输出都有明确 schema，模型输出校验失败时记录 `validation_errors` 并使用 fallback。
2. 证据检索 Agent 负责集中产生共享 EvidenceLedger，后续角色从 EvidenceLedger 读取证据，不重复拼接散乱事件列表。
3. 角色状态能区分：
   - 是否请求联网：`web_search_requested`
   - 是否实际联网：`used_web_search`
   - 联网结果：`web_search_status`
   - 是否使用 fallback：`fallback_used`
   - fallback 原因：`fallback_reason`
   - JSON/schema 校验错误：`validation_errors`
4. 报告级 `web_search_status` 仍保持兼容：任一角色实际联网为 `used`，否则任一角色不支持为 `unsupported`，否则 `disabled`。
5. 前端研究流水线展示不再把“没请求联网”“请求了但未实际调用”“网关不支持”“schema 失败后 fallback”混为一类。

## File Structure

- Create: `backend/app/services/analysis_agent_schemas.py`
  定义 EvidenceLedger、EvidenceItem、各角色输出 Pydantic schema、schema 校验工具。

- Create: `backend/app/services/analysis_agent_roles.py`
  定义 RoleSpec、角色列表、prompt builder、fallback builder、角色依赖关系。

- Modify: `backend/app/services/analysis_orchestrator_service.py`
  将大函数拆成基于 RoleSpec 的执行器；引入 EvidenceLedger；保留 `FunctionalAnalysisResult` 与 `FunctionalRoleResult` 对外契约。

- Modify: `backend/app/models/analysis_agent_run.py`
  新增状态字段：`web_search_requested`、`fallback_used`、`fallback_reason`、`validation_errors`。

- Modify: `backend/app/db/init_db.py`
  bootstrap schema 增加新列。

- Create: `backend/alembic/versions/20260529_0011_agent_role_status_fields.py`
  为 `analysis_agent_runs` 添加新列。

- Modify: `backend/app/services/analysis_repository.py`
  `create_analysis_agent_run()` 写入新增字段，列表读取不破坏旧数据。

- Modify: `backend/app/services/analysis_report_serializer.py`
  序列化 `pipeline_roles` 时包含新增字段，旧记录默认安全值。

- Modify: `backend/app/schemas/analysis.py`
  API schema 增加可选字段，保持旧前端兼容。

- Modify: `backend/app/services/analysis_service.py`
  落库角色运行记录时传递新增字段。

- Modify: `frontend/src/api/analysis.ts`
  TypeScript 类型补充新增字段。

- Modify: `frontend/src/views/AnalysisWorkbenchView.vue`
  研究流水线展示新增状态，不改页面主结构。

- Modify/Test:
  - `backend/tests/test_analysis_agent_schemas.py`
  - `backend/tests/test_analysis_orchestrator_service.py`
  - `backend/tests/test_analysis_service.py`
  - `backend/tests/test_alembic_baseline_smoke.py`
  - `frontend/src/views/AnalysisWorkbenchView.test.ts`

---

## Task 1: Define Pydantic Schemas and EvidenceLedger

**Files:**
- Create: `backend/app/services/analysis_agent_schemas.py`
- Test: `backend/tests/test_analysis_agent_schemas.py`

- [ ] **Step 1: Write failing schema tests**

Create `backend/tests/test_analysis_agent_schemas.py`:

```python
from pydantic import ValidationError

from app.services.analysis_agent_schemas import (
    ChallengeOutput,
    EvidenceItem,
    EvidenceLedger,
    HypothesisOutput,
    PlannerOutput,
    validate_role_output,
)


def test_evidence_ledger_normalizes_required_fields() -> None:
    ledger = EvidenceLedger(
        summary="已整理证据",
        items=[
            EvidenceItem(
                evidence_id="web:1",
                bucket="stock_news",
                title="公司发布经营进展",
                summary="公开报道显示经营进展改善。",
                source="证券时报",
                provider="web_search",
                url="https://example.com/news",
                published_at="2026-05-29T09:00:00+00:00",
                is_structured=False,
                is_web_search=True,
                claim="经营进展改善",
                relevance="用于验证偏多假设",
            )
        ],
    )

    assert ledger.items[0].is_web_search is True
    assert ledger.items[0].provider == "web_search"


def test_planner_output_rejects_invalid_shape() -> None:
    with pytest.raises(ValidationError):
        PlannerOutput(summary="缺字段")


def test_validate_role_output_returns_errors_and_fallback() -> None:
    fallback = {
        "summary": "fallback",
        "hypotheses": [
            {
                "key": "neutral_hypothesis",
                "title": "中性观察",
                "summary": "证据不足",
                "support_points": [],
                "counter_points": [],
                "confidence": "medium",
                "base_score": 1,
            }
        ],
    }

    payload, errors, fallback_used = validate_role_output(
        HypothesisOutput,
        {"summary": "bad", "hypotheses": "not-list"},
        fallback,
    )

    assert fallback_used is True
    assert errors
    assert payload["summary"] == "fallback"


def test_challenge_output_requires_challenge_items() -> None:
    with pytest.raises(ValidationError):
        ChallengeOutput(summary="缺少 challenges", challenges="bad")
```

Add missing `import pytest` at top.

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_agent_schemas.py
```

Expected: fail because `analysis_agent_schemas.py` does not exist.

- [ ] **Step 3: Implement schemas**

Create `backend/app/services/analysis_agent_schemas.py`:

```python
from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError


class EvidenceItem(BaseModel):
    evidence_id: str
    bucket: str
    title: str
    summary: str = ""
    source: str = ""
    provider: str = ""
    url: str | None = None
    published_at: str | None = None
    ts_code: str | None = None
    topic: str | None = None
    event_type: str | None = None
    source_priority: int | None = None
    is_structured: bool = False
    is_web_search: bool = False
    claim: str | None = None
    relevance: str | None = None


class EvidenceLedger(BaseModel):
    summary: str
    bucket_counts: dict[str, int] = Field(default_factory=dict)
    total_items: int | None = None
    items: list[EvidenceItem] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    summary: str
    focus_buckets: list[str]
    priority_questions: list[str]
    web_search_recommended: bool = False
    evidence_targets: list[dict[str, object]] = Field(default_factory=list)


class AuditOutput(BaseModel):
    summary: str
    overall_quality: Literal["high", "medium", "low"]
    duplicate_title_count: int = 0
    conflict_count: int = 0
    gap_count: int = 0
    gaps: list[str] = Field(default_factory=list)
    scorecard: dict[str, object] = Field(default_factory=dict)


class HypothesisItem(BaseModel):
    key: str
    title: str
    summary: str
    support_points: list[str] = Field(default_factory=list)
    counter_points: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    base_score: int | float = 0


class HypothesisOutput(BaseModel):
    summary: str
    hypotheses: list[HypothesisItem]


class ChallengeItem(BaseModel):
    hypothesis_key: str
    summary: str
    weakness_points: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    reduction_score: int | float = 0
    remaining_score: int | float = 0


class ChallengeOutput(BaseModel):
    summary: str
    challenges: list[ChallengeItem]


RoleSchema = TypeVar("RoleSchema", bound=BaseModel)


def validate_role_output(
    schema: type[RoleSchema],
    candidate: dict[str, object] | None,
    fallback: dict[str, object],
) -> tuple[dict[str, object], list[str], bool]:
    # 关键流程：模型 JSON 只能在 schema 校验通过后进入后续角色；
    # 校验失败时回退到规则输出，并保留错误用于流水线诊断。
    if candidate is None:
        return fallback, ["模型未返回可解析 JSON"], True
    try:
        return schema.model_validate(candidate).model_dump(mode="json"), [], False
    except ValidationError as exc:
        return fallback, [str(error) for error in exc.errors()], True
```

- [ ] **Step 4: Run test and verify pass**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_agent_schemas.py
```

Expected: pass.

---

## Task 2: Add RoleSpec Definitions

**Files:**
- Create: `backend/app/services/analysis_agent_roles.py`
- Test: `backend/tests/test_analysis_orchestrator_service.py`

- [ ] **Step 1: Add failing RoleSpec test**

Append to `backend/tests/test_analysis_orchestrator_service.py`:

```python
from app.services.analysis_agent_roles import FUNCTIONAL_ROLE_SPECS


def test_functional_role_specs_are_ordered_and_schema_backed() -> None:
    assert [item.role_key for item in FUNCTIONAL_ROLE_SPECS] == [
        "research_planner",
        "evidence_retrieval",
        "evidence_audit",
        "hypothesis_builder",
        "challenge_agent",
        "decision_agent",
    ]
    assert all(item.output_schema is not None for item in FUNCTIONAL_ROLE_SPECS[:-1])
    assert FUNCTIONAL_ROLE_SPECS[-1].output_schema is None
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_orchestrator_service.py::test_functional_role_specs_are_ordered_and_schema_backed
```

Expected: fail because `analysis_agent_roles.py` does not exist.

- [ ] **Step 3: Implement RoleSpec**

Create `backend/app/services/analysis_agent_roles.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.services.analysis_agent_schemas import (
    AuditOutput,
    ChallengeOutput,
    EvidenceLedger,
    HypothesisOutput,
    PlannerOutput,
)


@dataclass(frozen=True)
class RoleSpec:
    role_key: str
    role_label: str
    sort_order: int
    output_schema: type[BaseModel] | None
    system_instruction: str
    prompt_builder: Callable[[dict[str, object]], str]
    requires_web_search: bool = True


def _prompt(name: str) -> Callable[[dict[str, object]], str]:
    def build(context: dict[str, object]) -> str:
        return str(context[name])

    return build


FUNCTIONAL_ROLE_SPECS: list[RoleSpec] = [
    RoleSpec(
        role_key="research_planner",
        role_label="研究规划",
        sort_order=1,
        output_schema=PlannerOutput,
        system_instruction="你是研究规划 Agent，只能输出 JSON，不允许给投资建议。若联网增强开启，请优先检索最新公开信息来校准研究问题。",
        prompt_builder=_prompt("planner_prompt"),
    ),
    RoleSpec(
        role_key="evidence_retrieval",
        role_label="证据检索",
        sort_order=2,
        output_schema=EvidenceLedger,
        system_instruction="你是证据检索 Agent，只能输出 JSON。若联网增强开启，请集中检索最新公开报道、公告或权威来源，并输出 EvidenceLedger。",
        prompt_builder=_prompt("retrieval_prompt"),
    ),
    RoleSpec(
        role_key="evidence_audit",
        role_label="证据审计",
        sort_order=3,
        output_schema=AuditOutput,
        system_instruction="你是证据审计 Agent，只能输出 JSON。请核验证据缺口、冲突、过期信息和来源质量。",
        prompt_builder=_prompt("audit_prompt"),
    ),
    RoleSpec(
        role_key="hypothesis_builder",
        role_label="候选假设",
        sort_order=4,
        output_schema=HypothesisOutput,
        system_instruction="你是候选假设 Agent，只能输出 JSON，必须同时给出 bullish_hypothesis、neutral_hypothesis、bearish_hypothesis。",
        prompt_builder=_prompt("hypothesis_prompt"),
    ),
    RoleSpec(
        role_key="challenge_agent",
        role_label="反向质询",
        sort_order=5,
        output_schema=ChallengeOutput,
        system_instruction="你是反向质询 Agent，只能输出 JSON。请检索或识别反向证据和未覆盖风险，避免结论单边化。",
        prompt_builder=_prompt("challenge_prompt"),
    ),
    RoleSpec(
        role_key="decision_agent",
        role_label="最终裁决",
        sort_order=6,
        output_schema=None,
        system_instruction="你是最终裁决 Agent，负责把研究流水线结论整理为用户可读的中文 Markdown 报告。只输出 Markdown。",
        prompt_builder=_prompt("decision_prompt"),
    ),
]
```

- [ ] **Step 4: Run test and verify pass**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_orchestrator_service.py::test_functional_role_specs_are_ordered_and_schema_backed
```

Expected: pass.

---

## Task 3: Upgrade Orchestrator to RoleSpec + Shared EvidenceLedger

**Files:**
- Modify: `backend/app/services/analysis_orchestrator_service.py`
- Test: `backend/tests/test_analysis_orchestrator_service.py`

- [ ] **Step 1: Add failing tests for EvidenceLedger sharing**

Add tests:

```python
def test_evidence_ledger_from_retrieval_is_shared_by_later_roles(monkeypatch) -> None:
    prompts: list[str] = []

    async def fake_generate_llm_result(prompt: str, **kwargs) -> LlmTextResult:
        prompts.append(prompt)
        if "EvidenceLedger" in prompt or "证据账本 JSON" in prompt:
            text = json.dumps({
                "summary": "联网证据已集中整理",
                "bucket_counts": {"stock_news": 1},
                "total_items": 1,
                "items": [{
                    "evidence_id": "web:1",
                    "bucket": "stock_news",
                    "title": "联网来源标题",
                    "summary": "联网来源摘要",
                    "source": "测试媒体",
                    "provider": "web_search",
                    "url": "https://example.com/web-1",
                    "published_at": "2026-05-29T09:00:00+00:00",
                    "is_structured": False,
                    "is_web_search": True,
                    "claim": "经营改善",
                    "relevance": "验证偏多假设",
                }],
            })
        elif "候选假设" in str(kwargs.get("system_instruction", "")):
            text = json.dumps({
                "summary": "已生成假设",
                "hypotheses": [{
                    "key": "neutral_hypothesis",
                    "title": "中性观察",
                    "summary": "证据仍需观察",
                    "support_points": ["联网来源标题"],
                    "counter_points": [],
                    "confidence": "medium",
                    "base_score": 1,
                }],
            })
        elif "反向质询" in str(kwargs.get("system_instruction", "")):
            text = json.dumps({
                "summary": "已完成质询",
                "challenges": [{
                    "hypothesis_key": "neutral_hypothesis",
                    "summary": "仍需跟踪",
                    "weakness_points": [],
                    "unresolved_questions": ["联网来源是否持续更新"],
                    "reduction_score": 0,
                    "remaining_score": 1,
                }],
            })
        elif "证据审计" in str(kwargs.get("system_instruction", "")):
            text = json.dumps({
                "summary": "证据质量中等",
                "overall_quality": "medium",
                "duplicate_title_count": 0,
                "conflict_count": 0,
                "gap_count": 0,
                "gaps": [],
                "scorecard": {"web_item_count": 1},
            })
        else:
            text = json.dumps({
                "summary": "计划完成",
                "focus_buckets": ["stock_news"],
                "priority_questions": ["检索最新公开信息"],
                "web_search_recommended": True,
                "evidence_targets": [{"bucket": "stock_news", "limit": 3}],
            })
        return LlmTextResult(text=text, used_web_search=True, web_search_status="used", web_sources=[], model_name="test", reasoning_effort="medium", token_usage_input=1, token_usage_output=1)

    async def fake_generate_streamed_llm_result(prompt: str, **kwargs) -> LlmTextResult:
        prompts.append(prompt)
        on_delta = kwargs.get("on_delta")
        if on_delta is not None:
            await on_delta("## 核心判断\n使用联网证据。")
        return LlmTextResult(text="## 核心判断\n使用联网证据。", used_web_search=True, web_search_status="used", web_sources=[], model_name="test", reasoning_effort="medium", token_usage_input=1, token_usage_output=1)

    monkeypatch.setattr("app.services.analysis_orchestrator_service.generate_llm_result", fake_generate_llm_result)
    monkeypatch.setattr("app.services.analysis_orchestrator_service.generate_streamed_llm_result", fake_generate_streamed_llm_result)

    async def run_test() -> None:
        result = await run_functional_multi_agent_analysis(
            session=SimpleNamespace(),
            session_row=SimpleNamespace(ts_code="600519.SH", topic=None, use_web_search=True),
            instrument=SimpleNamespace(name="贵州茅台"),
            latest_snapshot=None,
            event_payloads=[],
            factor_weights=[],
        )

        retrieval = next(role for role in result.pipeline_roles if role.role_key == "evidence_retrieval")
        assert retrieval.output_payload["items"][0]["title"] == "联网来源标题"
        assert any("联网来源标题" in prompt for prompt in prompts if "候选假设" in prompt or "反向质询" in prompt)
        assert result.web_sources or retrieval.output_payload["items"][0]["is_web_search"] is True

    asyncio.run(run_test())
```

- [ ] **Step 2: Run test and verify failure or current weak behavior**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_orchestrator_service.py::test_evidence_ledger_from_retrieval_is_shared_by_later_roles
```

Expected: fail until prompts and shared ledger are wired.

- [ ] **Step 3: Refactor context builders**

In `analysis_orchestrator_service.py`, add helpers:

```python
def _build_initial_evidence_ledger(*, session_row, latest_snapshot, event_payloads: list[dict[str, object]]) -> dict[str, object]:
    items: list[dict[str, object]] = []
    bucket_counts: dict[str, int] = {}
    for item in event_payloads:
        event_type = str(item.get("event_type") or "").lower()
        bucket = "policy_documents" if event_type == "policy" else "announcements" if event_type == "announcement" else "stock_news"
        evidence = {
            "evidence_id": str(item.get("event_id") or ""),
            "bucket": bucket,
            "title": str(item.get("title") or ""),
            "summary": str(item.get("summary") or item.get("title") or ""),
            "published_at": item.get("published_at"),
            "source": str(item.get("source") or ""),
            "provider": str(item.get("source") or ""),
            "url": item.get("url"),
            "ts_code": session_row.ts_code,
            "topic": session_row.topic,
            "event_type": item.get("event_type"),
            "source_priority": item.get("source_priority"),
            "is_structured": True,
            "is_web_search": False,
        }
        items.append(evidence)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    if latest_snapshot is not None:
        items.append({
            "evidence_id": f"snapshot:{session_row.ts_code}",
            "bucket": "price_and_volume",
            "title": f"{session_row.ts_code} 最新行情快照",
            "summary": f"收盘价 {getattr(latest_snapshot, 'close', None)}，涨跌幅 {getattr(latest_snapshot, 'pct_chg', None)}",
            "source": "stock_daily_snapshots",
            "provider": "tushare",
            "published_at": to_json_safe_payload(getattr(latest_snapshot, "trade_date", None)),
            "is_structured": True,
            "is_web_search": False,
        })
        bucket_counts["price_and_volume"] = bucket_counts.get("price_and_volume", 0) + 1
    return {"summary": "已整理初始结构化证据。", "bucket_counts": bucket_counts, "total_items": len(items), "items": items}
```

Add prompt context:

```python
def _json_text(value: object) -> str:
    return json.dumps(to_json_safe_payload(value), ensure_ascii=False)
```

- [ ] **Step 4: Use EvidenceLedger as shared state**

Update `run_functional_multi_agent_analysis()` so:

1. Build `initial_ledger = _build_initial_evidence_ledger(...)`.
2. Planner uses `initial_ledger`.
3. Retrieval fallback is `initial_ledger`, retrieval output becomes `evidence_ledger`.
4. Audit prompt uses `evidence_ledger`.
5. Hypothesis prompt uses `evidence_ledger` and `audit.output_payload`.
6. Challenge prompt uses `evidence_ledger` and `hypotheses.output_payload`.
7. Decision prompt uses `evidence_ledger`, `audit`, `hypotheses`, `challenge`, and `decision`.

Required prompt fragments:

```python
retrieval_prompt = (
    f"请围绕 {session_row.ts_code} 输出 EvidenceLedger JSON，字段必须包含 "
    "summary、bucket_counts、total_items、items。"
    f"初始结构化证据：{_json_text(initial_ledger)}"
)
```

```python
hypothesis_prompt = (
    f"请围绕 {session_row.ts_code} 输出三种候选假设 JSON。"
    f"共享 EvidenceLedger：{_json_text(evidence_ledger)}"
    f"证据审计：{_json_text(audit.output_payload)}"
)
```

```python
challenge_prompt = (
    f"请对 {session_row.ts_code} 的候选假设做反向质询 JSON。"
    f"共享 EvidenceLedger：{_json_text(evidence_ledger)}"
    f"候选假设：{_json_text(hypothesis_items)}"
)
```

- [ ] **Step 5: Merge web sources from EvidenceLedger**

Add helper:

```python
def _web_sources_from_evidence_ledger(ledger: dict[str, object]) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in ledger.get("items") or []:
        if not isinstance(item, dict) or not item.get("is_web_search"):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append({
            "title": item.get("title"),
            "url": url,
            "source": item.get("source") or item.get("provider"),
            "published_at": item.get("published_at"),
            "snippet": item.get("summary"),
        })
    return sources
```

Use this when building `all_sources`.

- [ ] **Step 6: Run orchestrator tests**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_orchestrator_service.py tests/test_analysis_agent_schemas.py
```

Expected: pass.

---

## Task 4: Add Status Fields to Database and Repository

**Files:**
- Modify: `backend/app/models/analysis_agent_run.py`
- Modify: `backend/app/db/init_db.py`
- Create: `backend/alembic/versions/20260529_0011_agent_role_status_fields.py`
- Modify: `backend/app/services/analysis_repository.py`
- Test: `backend/tests/test_alembic_baseline_smoke.py`
- Test: `backend/tests/test_analysis_service.py`

- [ ] **Step 1: Add failing persistence test**

Add to `backend/tests/test_analysis_service.py` a focused assertion in existing functional pipeline persistence test:

```python
assert persisted_role.web_search_requested is True
assert persisted_role.fallback_used is False
assert persisted_role.fallback_reason is None
assert persisted_role.validation_errors == []
```

If the existing fake role does not set these attributes, update the fake role payload to include:

```python
"web_search_requested": True,
"fallback_used": False,
"fallback_reason": None,
"validation_errors": [],
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_service.py::test_run_analysis_session_by_id_persists_functional_pipeline_roles
```

Expected: fail because model/repository fields do not exist.

- [ ] **Step 3: Update model**

In `backend/app/models/analysis_agent_run.py`, add:

```python
web_search_requested: Mapped[bool] = mapped_column(Boolean, default=False)
fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
fallback_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
validation_errors: Mapped[list[object]] = mapped_column(JSON, default=list)
```

- [ ] **Step 4: Update init_db bootstrap**

In `backend/app/db/init_db.py`, add columns for `analysis_agent_runs`:

```python
"web_search_requested": "BOOLEAN DEFAULT FALSE",
"fallback_used": "BOOLEAN DEFAULT FALSE",
"fallback_reason": "VARCHAR(64)",
"validation_errors": "JSON DEFAULT '[]'",
```

Use the repository's existing style for JSON defaults if SQLite/Postgres differs.

- [ ] **Step 5: Add Alembic migration**

Create `backend/alembic/versions/20260529_0011_agent_role_status_fields.py`:

```python
"""add agent role status fields

Revision ID: 20260529_0011
Revises: 20260528_0010
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_0011"
down_revision = "20260528_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_agent_runs", sa.Column("web_search_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("analysis_agent_runs", sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("analysis_agent_runs", sa.Column("fallback_reason", sa.String(length=64), nullable=True))
    op.add_column("analysis_agent_runs", sa.Column("validation_errors", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("analysis_agent_runs", "validation_errors")
    op.drop_column("analysis_agent_runs", "fallback_reason")
    op.drop_column("analysis_agent_runs", "fallback_used")
    op.drop_column("analysis_agent_runs", "web_search_requested")
```

If current migration head is not `20260528_0010`, adjust `down_revision` to the actual latest head after checking:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run alembic heads
```

- [ ] **Step 6: Update repository signature**

In `create_analysis_agent_run()`, add parameters:

```python
web_search_requested: bool = False,
fallback_used: bool = False,
fallback_reason: str | None = None,
validation_errors: list[object] | None = None,
```

Set row fields:

```python
web_search_requested=web_search_requested,
fallback_used=fallback_used,
fallback_reason=fallback_reason,
validation_errors=validation_errors or [],
```

- [ ] **Step 7: Run backend persistence tests**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_service.py::test_run_analysis_session_by_id_persists_functional_pipeline_roles tests/test_alembic_baseline_smoke.py
```

Expected: pass.

---

## Task 5: Carry Status Fields Through Role Execution and API Serialization

**Files:**
- Modify: `backend/app/services/analysis_orchestrator_service.py`
- Modify: `backend/app/services/analysis_service.py`
- Modify: `backend/app/services/analysis_report_serializer.py`
- Modify: `backend/app/schemas/analysis.py`
- Test: `backend/tests/test_analysis_orchestrator_service.py`
- Test: `backend/tests/test_analysis_service.py`

- [ ] **Step 1: Extend FunctionalRoleResult**

Add fields:

```python
web_search_requested: bool
fallback_used: bool
fallback_reason: str | None
validation_errors: list[str]
```

Place them near existing `used_web_search/web_search_status` fields.

- [ ] **Step 2: Update `_run_json_role()`**

Use `validate_role_output()`:

```python
candidate = _try_parse_json(llm.text)
payload, validation_errors, fallback_used = validate_role_output(
    output_schema,
    candidate,
    fallback,
)
fallback_reason = "schema_validation_failed" if fallback_used else None
```

For exceptions:

```python
fallback_used = True
fallback_reason = "llm_exception"
validation_errors = [type(exc).__name__]
```

Set:

```python
web_search_requested=use_web_search
```

- [ ] **Step 3: Update decision role status**

For `decision_agent`, set:

```python
web_search_requested=role_web_search_enabled,
fallback_used=decision_failure_type is not None,
fallback_reason="llm_exception" if decision_failure_type else None,
validation_errors=[],
```

- [ ] **Step 4: Persist new fields in analysis_service**

When calling `create_analysis_agent_run()`, pass:

```python
web_search_requested=getattr(role_obj, "web_search_requested", False),
fallback_used=getattr(role_obj, "fallback_used", False),
fallback_reason=getattr(role_obj, "fallback_reason", None),
validation_errors=_normalize_json_list(getattr(role_obj, "validation_errors", None)),
```

- [ ] **Step 5: Serialize new fields**

In `analysis_report_serializer.py`, each pipeline role includes:

```python
"web_search_requested": getattr(role_obj, "web_search_requested", False),
"fallback_used": getattr(role_obj, "fallback_used", False),
"fallback_reason": getattr(role_obj, "fallback_reason", None),
"validation_errors": getattr(role_obj, "validation_errors", []) or [],
```

- [ ] **Step 6: Update API schema**

In `backend/app/schemas/analysis.py`, role response model adds:

```python
web_search_requested: bool = False
fallback_used: bool = False
fallback_reason: str | None = None
validation_errors: list[object] = []
```

- [ ] **Step 7: Add tests**

Add orchestrator tests:

```python
def test_role_records_validation_fallback_status(monkeypatch) -> None:
    # mock evidence_audit to return invalid schema and assert fallback_used/validation_errors.
```

Concrete assertions:

```python
audit_role = next(role for role in result.pipeline_roles if role.role_key == "evidence_audit")
assert audit_role.fallback_used is True
assert audit_role.fallback_reason == "schema_validation_failed"
assert audit_role.validation_errors
assert audit_role.status == "completed"
```

Add persistence assertions:

```python
assert persisted_role.web_search_requested is True
assert persisted_role.fallback_used is False
assert persisted_role.validation_errors == []
```

- [ ] **Step 8: Run tests**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_orchestrator_service.py tests/test_analysis_service.py tests/test_analysis_agent_schemas.py
```

Expected: pass.

---

## Task 6: Frontend Types and Pipeline Status Display

**Files:**
- Modify: `frontend/src/api/analysis.ts`
- Modify: `frontend/src/views/AnalysisWorkbenchView.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Test: `frontend/src/views/AnalysisWorkbenchView.test.ts`

- [ ] **Step 1: Update TypeScript types**

In `AnalysisPipelineRole` add:

```typescript
web_search_requested?: boolean
fallback_used?: boolean
fallback_reason?: string | null
validation_errors?: unknown[]
```

- [ ] **Step 2: Add i18n labels**

Chinese:

```typescript
roleWebSearchRequested: '已请求联网',
roleWebSearchNotRequested: '未请求联网',
roleFallbackUsed: '已使用降级结果',
roleValidationWarning: '输出校验异常',
```

English:

```typescript
roleWebSearchRequested: 'Web search requested',
roleWebSearchNotRequested: 'Web search not requested',
roleFallbackUsed: 'Fallback used',
roleValidationWarning: 'Output validation warning',
```

- [ ] **Step 3: Display status badges**

In role pipeline rendering near existing `role.web_search_status`, show:

```vue
<span class="analysis-role-chip">
  {{ role.web_search_requested ? t('analysisWorkbench.roleWebSearchRequested') : t('analysisWorkbench.roleWebSearchNotRequested') }}
</span>
<span v-if="role.fallback_used" class="analysis-role-chip warning">
  {{ t('analysisWorkbench.roleFallbackUsed') }}
</span>
<span v-if="role.validation_errors?.length" class="analysis-role-chip warning">
  {{ t('analysisWorkbench.roleValidationWarning') }}
</span>
```

- [ ] **Step 4: Add frontend test**

In `AnalysisWorkbenchView.test.ts`, create a report with one role:

```typescript
{
  role_key: 'evidence_audit',
  role_label: '证据审计',
  status: 'completed',
  sort_order: 3,
  summary: '已使用 fallback',
  output_payload: {},
  used_web_search: false,
  web_search_requested: true,
  web_search_status: 'unsupported',
  fallback_used: true,
  fallback_reason: 'schema_validation_failed',
  validation_errors: ['field required'],
}
```

Assert:

```typescript
expect(wrapper.text()).toContain('已请求联网')
expect(wrapper.text()).toContain('已使用降级结果')
expect(wrapper.text()).toContain('输出校验异常')
```

- [ ] **Step 5: Run frontend tests**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/views/AnalysisWorkbenchView.test.ts
npm run build
```

Expected: pass.

---

## Task 7: Full Verification and Regression

**Files:**
- No new files unless tests expose issues.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_agent_schemas.py tests/test_analysis_orchestrator_service.py tests/test_analysis_service.py tests/test_llm_client_service.py tests/test_alembic_baseline_smoke.py
```

Expected: all pass.

- [ ] **Step 2: Run full backend tests if focused suite passes**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\backend'
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 3: Run frontend tests and build**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/views/AnalysisWorkbenchView.test.ts
npm run build
```

Expected: all pass.

- [ ] **Step 4: Manual smoke test**

Start app:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject'
.\start-dev.bat
```

Open:

```text
http://localhost:5173/analysis?ts_code=000001.SZ&source=stock_detail
```

Manual checks:

- 开启“本次分析联网增强”。
- 点击“刷新分析”。
- 研究流水线应展示 6 个角色。
- 证据检索角色应包含 EvidenceLedger 风格输出。
- 各角色应区分“已请求联网”和“实际联网状态”。
- 如果有 fallback，应显示“已使用降级结果”，但报告不应因为普通 fallback 成功而误标不完整。

- [ ] **Step 5: Diff check**

Run:

```powershell
Set-Location -Path 'E:\Development\Project\StockProject'
git diff --check
```

Expected: no whitespace errors. LF/CRLF warnings are acceptable if no whitespace error.

---

## Rollout Notes

- 旧报告的 `analysis_agent_runs` 没有新增状态字段，序列化时应默认：
  - `web_search_requested=false`
  - `fallback_used=false`
  - `fallback_reason=null`
  - `validation_errors=[]`
- 新报告才会展示完整状态。
- 如果生产数据库已有旧迁移 head，执行前先确认 Alembic head，避免 `down_revision` 接错。
- 本计划会增加 LLM 调用的结构化约束，但不会减少调用次数。后续若需要控成本，应另开计划做“证据检索集中联网、后续角色默认不补搜，只有缺口触发补搜”的策略开关。

## Acceptance Criteria

- RoleSpec 文件存在，6 个角色定义集中管理。
- 每个 JSON 角色都有 Pydantic schema 校验。
- EvidenceLedger 成为证据检索输出和后续角色共享输入。
- `analysis_agent_runs` 持久化新增状态字段。
- API 返回 pipeline_roles 时包含新增状态字段。
- 前端研究流水线能展示请求联网、实际联网、fallback、校验异常。
- Focused backend tests、full backend tests、frontend workbench tests、frontend build 通过。
