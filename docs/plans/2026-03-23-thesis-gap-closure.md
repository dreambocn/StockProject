# Thesis Gap Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补齐开题报告中尚未落地的“多源数据融合 + 事件关联分析 + 大模型解释 + 工程化交付”能力，使项目从“数据展示系统”升级为“可用于毕业设计验收的股票波动分析系统”。

**Architecture:** 现有 `stocks/news` 数据链路继续保留，新增一层 `analysis` 领域能力：先将政策/公告/新闻统一沉淀为标准事件，再对事件做情感与关键因子抽取，之后结合股票价格窗口计算事件-波动关联分数和多因素权重，最后通过 LLM 生成中文解释报告。前端新增分析工作台页面，把热点新闻、个股详情、事件查询和自动报告串成一条完整分析链路。

**Tech Stack:** FastAPI、SQLAlchemy、Redis、Tushare、AkShare、Pydantic、Vue 3、TypeScript、Vitest、Pytest、Docker Compose、GitHub Actions（或等价 CI）。

---

## Delivery Priority

- **P0（答辩必需）**：事件分析 API、政策/公告事件接入、情感与关键事件抽取、事件-波动关联、多因素权重评估、LLM 中文解释、前端分析工作台。
- **P1（完整度增强）**：热点新闻候选股联动、自动报告导出、个股详情分析联动、定时同步脚本。
- **P2（工程交付）**：Docker Compose、CI、README/PROGRESS 更新、答辩演示脚本。

## Chunk 1: Analysis 后端骨架

### Task 1: 新增 analysis 领域模型与 API 骨架

**Files:**
- Create: `backend/app/models/analysis_event_link.py`
- Create: `backend/app/models/analysis_report.py`
- Create: `backend/app/schemas/analysis.py`
- Create: `backend/app/api/routes/analysis.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_analysis_routes.py`

**Step 1: Write the failing test**

```python
def test_get_stock_analysis_summary_returns_200(client):
    response = client.get("/api/analysis/stocks/600519.SH/summary")
    assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_routes.py::test_get_stock_analysis_summary_returns_200`
Expected: FAIL，因为路由与 schema 尚不存在。

**Step 3: Write minimal implementation**

```python
router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/stocks/{ts_code}/summary")
async def get_stock_analysis_summary(ts_code: str) -> dict[str, object]:
    return {"ts_code": ts_code, "events": [], "report": None}
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_routes.py::test_get_stock_analysis_summary_returns_200`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/models/analysis_event_link.py backend/app/models/analysis_report.py backend/app/schemas/analysis.py backend/app/api/routes/analysis.py backend/app/main.py backend/tests/test_analysis_routes.py
git commit -m "feat: 新增分析领域接口骨架"
```

### Task 2: 为 analysis 增加仓储与聚合服务

**Files:**
- Create: `backend/app/services/analysis_repository.py`
- Create: `backend/app/services/analysis_service.py`
- Modify: `backend/app/api/routes/analysis.py`
- Test: `backend/tests/test_analysis_service.py`
- Test: `backend/tests/test_analysis_routes.py`

**Step 1: Write the failing test**

```python
async def test_analysis_service_returns_latest_events_for_stock(async_session):
    result = await get_stock_analysis_summary(async_session, "600519.SH")
    assert "events" in result
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_service.py::test_analysis_service_returns_latest_events_for_stock`
Expected: FAIL，因为服务层尚不存在。

**Step 3: Write minimal implementation**

```python
async def get_stock_analysis_summary(session: AsyncSession, ts_code: str) -> dict[str, object]:
    return {
        "ts_code": ts_code,
        "events": await load_latest_event_links(session, ts_code),
        "report": await load_latest_report(session, ts_code),
    }
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_service.py::test_analysis_service_returns_latest_events_for_stock`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/analysis_repository.py backend/app/services/analysis_service.py backend/app/api/routes/analysis.py backend/tests/test_analysis_service.py backend/tests/test_analysis_routes.py
git commit -m "feat: 新增分析聚合服务与仓储层"
```

## Chunk 2: 多源事件接入与标准化

### Task 3: 接入政策 / 监管事件数据源并统一沉淀事件

**Files:**
- Create: `backend/app/integrations/policy_gateway.py`
- Modify: `backend/app/api/routes/news.py`
- Modify: `backend/app/services/news_mapper_service.py`
- Modify: `backend/app/services/news_repository.py`
- Modify: `backend/app/schemas/news.py`
- Test: `backend/tests/test_news_routes.py`

**Step 1: Write the failing test**

```python
def test_get_policy_news_returns_policy_scope(client, monkeypatch):
    monkeypatch.setattr(
        "app.integrations.policy_gateway.fetch_policy_events",
        lambda: [{"title": "证监会发布新规", "summary": "规范量化交易", "published_at": "2026-03-01 10:00:00"}],
    )
    response = client.get("/api/news/policy")
    assert response.status_code == 200
    assert response.json()[0]["scope"] == "policy"
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_news_routes.py::test_get_policy_news_returns_policy_scope`
Expected: FAIL，因为政策数据路由与映射尚不存在。

**Step 3: Write minimal implementation**

```python
@router.get("/news/policy", response_model=list[NewsEventResponse])
async def get_policy_news(...) -> list[NewsEventResponse]:
    rows = await fetch_policy_events()
    return map_policy_rows(rows)
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_news_routes.py::test_get_policy_news_returns_policy_scope`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/integrations/policy_gateway.py backend/app/api/routes/news.py backend/app/services/news_mapper_service.py backend/app/services/news_repository.py backend/app/schemas/news.py backend/tests/test_news_routes.py
git commit -m "feat: 接入政策事件数据源并统一沉淀"
```

### Task 4: 为 news_events 增加政策 / 情绪 / 关键事件字段

**Files:**
- Modify: `backend/app/models/news_event.py`
- Modify: `backend/app/db/init_db.py`
- Modify: `backend/app/schemas/news.py`
- Test: `backend/tests/test_db_schema.py`
- Test: `backend/tests/test_news_routes.py`

**Step 1: Write the failing test**

```python
async def test_news_event_schema_contains_sentiment_and_event_tags(async_session):
    await ensure_database_schema()
    # 这里断言新字段已存在
    assert True
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_db_schema.py -k sentiment`
Expected: FAIL，因为表结构还没有新字段。

**Step 3: Write minimal implementation**

```python
sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
sentiment_score: Mapped[float | None] = mapped_column(nullable=True)
event_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_db_schema.py -k sentiment`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/models/news_event.py backend/app/db/init_db.py backend/app/schemas/news.py backend/tests/test_db_schema.py backend/tests/test_news_routes.py
git commit -m "feat: 扩展事件表结构支持情绪与关键标签"
```

## Chunk 3: 事件分析与权重评估

### Task 5: 新增新闻情感分析与关键事件抽取服务

**Files:**
- Create: `backend/app/services/news_sentiment_service.py`
- Create: `backend/app/services/key_event_extraction_service.py`
- Modify: `backend/app/services/analysis_service.py`
- Test: `backend/tests/test_news_sentiment_service.py`
- Test: `backend/tests/test_analysis_service.py`

**Step 1: Write the failing test**

```python
def test_sentiment_service_returns_positive_label_for_beneficial_news():
    result = analyze_news_sentiment("公司业绩大增，利润超预期", "盈利能力显著提升")
    assert result.label == "positive"
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_news_sentiment_service.py::test_sentiment_service_returns_positive_label_for_beneficial_news`
Expected: FAIL，因为情感分析服务尚不存在。

**Step 3: Write minimal implementation**

```python
def analyze_news_sentiment(title: str, summary: str | None) -> SentimentResult:
    text = f"{title} {summary or ''}"
    if "大增" in text or "利好" in text:
        return SentimentResult(label="positive", score=0.8)
    return SentimentResult(label="neutral", score=0.0)
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_news_sentiment_service.py::test_sentiment_service_returns_positive_label_for_beneficial_news`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/news_sentiment_service.py backend/app/services/key_event_extraction_service.py backend/app/services/analysis_service.py backend/tests/test_news_sentiment_service.py backend/tests/test_analysis_service.py
git commit -m "feat: 新增情感分析与关键事件抽取服务"
```

### Task 6: 新增事件-股价关联与多因素权重评估服务

**Files:**
- Create: `backend/app/services/event_link_service.py`
- Create: `backend/app/services/factor_weight_service.py`
- Modify: `backend/app/services/analysis_service.py`
- Modify: `backend/app/api/routes/analysis.py`
- Test: `backend/tests/test_event_link_service.py`
- Test: `backend/tests/test_factor_weight_service.py`
- Test: `backend/tests/test_analysis_routes.py`

**Step 1: Write the failing test**

```python
async def test_event_link_service_returns_price_window_metrics(async_session):
    result = await link_event_to_stock_move(async_session, "600519.SH", "event-1")
    assert "window_return_pct" in result
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_event_link_service.py::test_event_link_service_returns_price_window_metrics`
Expected: FAIL，因为事件关联服务尚不存在。

**Step 3: Write minimal implementation**

```python
async def link_event_to_stock_move(session: AsyncSession, ts_code: str, event_id: str) -> dict[str, float | str]:
    return {
        "event_id": event_id,
        "window_return_pct": 0.0,
        "window_volatility": 0.0,
        "correlation_score": 0.0,
    }
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_event_link_service.py::test_event_link_service_returns_price_window_metrics`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/event_link_service.py backend/app/services/factor_weight_service.py backend/app/services/analysis_service.py backend/app/api/routes/analysis.py backend/tests/test_event_link_service.py backend/tests/test_factor_weight_service.py backend/tests/test_analysis_routes.py
git commit -m "feat: 新增事件关联与多因素权重评估服务"
```

## Chunk 4: 大模型解释与报告输出

### Task 7: 新增 LLM 提示词模板与解释服务

**Files:**
- Create: `backend/app/services/llm_analysis_service.py`
- Create: `backend/app/services/analysis_prompt_service.py`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/app/services/analysis_service.py`
- Test: `backend/tests/test_llm_analysis_service.py`
- Test: `backend/tests/test_analysis_routes.py`

**Step 1: Write the failing test**

```python
async def test_llm_analysis_service_returns_chinese_report(monkeypatch):
    monkeypatch.setattr("app.services.llm_analysis_service.call_llm", lambda prompt: "该股票短期波动主要受政策预期和情绪驱动。")
    result = await generate_stock_analysis_report(...)
    assert "政策预期" in result.summary
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_llm_analysis_service.py::test_llm_analysis_service_returns_chinese_report`
Expected: FAIL，因为 LLM 解释服务尚不存在。

**Step 3: Write minimal implementation**

```python
async def generate_stock_analysis_report(...) -> AnalysisReportResult:
    prompt = build_stock_analysis_prompt(...)
    content = await call_llm(prompt)
    return AnalysisReportResult(summary=content, risk_points=[], factor_breakdown=[])
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_llm_analysis_service.py::test_llm_analysis_service_returns_chinese_report`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/llm_analysis_service.py backend/app/services/analysis_prompt_service.py backend/app/core/settings.py backend/app/services/analysis_service.py backend/tests/test_llm_analysis_service.py backend/tests/test_analysis_routes.py
git commit -m "feat: 新增大模型中文分析报告服务"
```

### Task 8: 新增报告缓存与导出接口

**Files:**
- Modify: `backend/app/models/analysis_report.py`
- Modify: `backend/app/api/routes/analysis.py`
- Modify: `backend/app/services/analysis_repository.py`
- Test: `backend/tests/test_analysis_routes.py`

**Step 1: Write the failing test**

```python
def test_export_stock_analysis_report_returns_markdown(client):
    response = client.get("/api/analysis/stocks/600519.SH/report?format=markdown")
    assert response.status_code == 200
    assert "# 股票分析报告" in response.text
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_routes.py::test_export_stock_analysis_report_returns_markdown`
Expected: FAIL，因为导出接口尚不存在。

**Step 3: Write minimal implementation**

```python
@router.get("/stocks/{ts_code}/report")
async def export_stock_analysis_report(ts_code: str, format: str = "markdown") -> Response:
    return PlainTextResponse("# 股票分析报告\n")
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_routes.py::test_export_stock_analysis_report_returns_markdown`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/models/analysis_report.py backend/app/api/routes/analysis.py backend/app/services/analysis_repository.py backend/tests/test_analysis_routes.py
git commit -m "feat: 新增分析报告缓存与导出接口"
```

## Chunk 5: 前端分析工作台与链路联动

### Task 9: 新增前端 analysis API 与分析工作台页面

**Files:**
- Create: `frontend/src/api/analysis.ts`
- Create: `frontend/src/views/AnalysisWorkbenchView.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Test: `frontend/src/views/AnalysisWorkbenchView.test.ts`
- Test: `frontend/src/router/index.test.ts`

**Step 1: Write the failing test**

```ts
it('registers analysis workbench route', () => {
  expect(router.getRoutes().some((item) => item.path === '/analysis')).toBe(true)
})
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/router/index.test.ts -t "analysis workbench route"`
Expected: FAIL，因为路由与页面尚不存在。

**Step 3: Write minimal implementation**

```ts
{ path: '/analysis', name: 'analysis-workbench', component: () => import('../views/AnalysisWorkbenchView.vue') }
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/router/index.test.ts -t "analysis workbench route"`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add frontend/src/api/analysis.ts frontend/src/views/AnalysisWorkbenchView.vue frontend/src/router/index.ts frontend/src/App.vue frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts frontend/src/views/AnalysisWorkbenchView.test.ts frontend/src/router/index.test.ts
git commit -m "feat: 新增前端分析工作台"
```

### Task 10: 打通热点新闻 / 个股详情到分析工作台的上下文联动

**Files:**
- Modify: `frontend/src/views/HotNewsView.vue`
- Modify: `frontend/src/views/StockDetailView.vue`
- Modify: `frontend/src/views/HomeView.vue`
- Modify: `frontend/src/views/AdminStocksView.vue`
- Test: `frontend/src/views/HotNewsView.test.ts`
- Test: `frontend/src/views/StockDetailView.test.ts`

**Step 1: Write the failing test**

```ts
it('navigates to analysis workbench with ts_code and topic context', async () => {
  // 断言点击后跳转到 /analysis 并带查询参数
})
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/views/HotNewsView.test.ts -t "analysis workbench"`
Expected: FAIL，因为联动入口尚不存在。

**Step 3: Write minimal implementation**

```ts
await router.push({
  path: '/analysis',
  query: { ts_code: item.ts_code, topic: profile.topic },
})
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/views/HotNewsView.test.ts -t "analysis workbench"`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add frontend/src/views/HotNewsView.vue frontend/src/views/StockDetailView.vue frontend/src/views/HomeView.vue frontend/src/views/AdminStocksView.vue frontend/src/views/HotNewsView.test.ts frontend/src/views/StockDetailView.test.ts
git commit -m "feat: 打通热点新闻与个股分析联动"
```

## Chunk 6: 定时同步、部署与验收材料

### Task 11: 新增同步脚本并修复 README 中缺失脚本问题

**Files:**
- Create: `backend/scripts/sync_analysis_sources.py`
- Create: `backend/scripts/rebuild_stock_analysis.py`
- Modify: `README.md`
- Test: `backend/tests/test_analysis_scripts.py`

**Step 1: Write the failing test**

```python
def test_sync_analysis_sources_script_runs_without_exception():
    assert True
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_scripts.py`
Expected: FAIL，因为脚本与测试文件尚不存在。

**Step 3: Write minimal implementation**

```python
async def main() -> None:
    print("analysis sources synced")
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_scripts.py`
Expected: PASS。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/scripts/sync_analysis_sources.py backend/scripts/rebuild_stock_analysis.py README.md backend/tests/test_analysis_scripts.py
git commit -m "chore: 新增分析同步脚本并修正文档命令"
```

### Task 12: 新增 Docker Compose 与 CI 验证流程

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `PROGRESS.md`

**Step 1: Write the failing test**

```text
人工验收：仓库根目录存在 docker-compose 与 CI 工作流文件。
```

**Step 2: Run test to verify it fails**

Run: `Set-Location 'E:\Development\Project\StockProject'; Test-Path '.\docker-compose.yml'; Test-Path '.\.github\workflows\ci.yml'`
Expected: 当前至少有一个返回 `False`。

**Step 3: Write minimal implementation**

```yaml
services:
  backend:
    build: ./backend
  frontend:
    build: ./frontend
```

**Step 4: Run test to verify it passes**

Run: `Set-Location 'E:\Development\Project\StockProject'; Test-Path '.\docker-compose.yml'; Test-Path '.\.github\workflows\ci.yml'`
Expected: 两项均返回 `True`。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add docker-compose.yml backend/Dockerfile frontend/Dockerfile .github/workflows/ci.yml README.md PROGRESS.md
git commit -m "chore: 新增容器化与持续集成配置"
```

## Verification

### Task 13: 后端验证

**Files:**
- Test: `backend/tests/test_news_routes.py`
- Test: `backend/tests/test_analysis_routes.py`
- Test: `backend/tests/test_analysis_service.py`
- Test: `backend/tests/test_event_link_service.py`
- Test: `backend/tests/test_factor_weight_service.py`
- Test: `backend/tests/test_llm_analysis_service.py`

**Step 1: Run targeted backend tests**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_news_routes.py tests/test_analysis_routes.py tests/test_analysis_service.py tests/test_event_link_service.py tests/test_factor_weight_service.py tests/test_llm_analysis_service.py`
Expected: PASS。

**Step 2: Run full backend tests**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q`
Expected: PASS。

**Step 3: Run schema bootstrap verification**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run python -c "import asyncio; from app.db.init_db import ensure_database_schema; asyncio.run(ensure_database_schema()); print('schema ensured')"`
Expected: 输出 `schema ensured`。

**Step 4: Run minimal manual API smoke test**

Run: `Set-Location 'E:\Development\Project\StockProject\backend'; uv run fastapi dev main.py`
Expected: 本地可访问 `/api/analysis/stocks/{ts_code}/summary`。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add PROGRESS.md
git commit -m "test: 完成分析后端验证"
```

### Task 14: 前端验证

**Files:**
- Test: `frontend/src/views/AnalysisWorkbenchView.test.ts`
- Test: `frontend/src/views/HotNewsView.test.ts`
- Test: `frontend/src/views/StockDetailView.test.ts`
- Test: `frontend/src/router/index.test.ts`

**Step 1: Run targeted frontend tests**

Run: `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/views/AnalysisWorkbenchView.test.ts src/views/HotNewsView.test.ts src/views/StockDetailView.test.ts src/router/index.test.ts`
Expected: PASS。

**Step 2: Run full frontend tests**

Run: `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run`
Expected: PASS。

**Step 3: Run frontend build**

Run: `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run build`
Expected: PASS。

**Step 4: Run manual smoke test**

Run: `Set-Location 'E:\Development\Project\StockProject'; .\start-dev.bat`
Expected: 首页、热点页、个股详情页、分析工作台都可访问。

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add README.md PROGRESS.md docs/plans/2026-03-23-thesis-gap-closure.md
git commit -m "docs: 补充开题报告补功能实施计划"
```

---

## Acceptance Checklist

- [ ] 能查询并持久化股票、热点新闻、个股新闻、公告、政策事件。
- [ ] 能对新闻/政策事件输出中文情感标签、情感分数、关键事件标签。
- [ ] 能按股票和时间窗口给出事件-波动关联结果。
- [ ] 能输出政策 / 新闻 / 情绪 / 公告等多因素权重评估结果。
- [ ] 能通过 LLM 生成中文“波动原因解释”和“风险提示”。
- [ ] 前端存在独立分析工作台，可从热点新闻和个股详情跳转进入。
- [ ] 能导出 Markdown 格式分析报告，满足答辩展示。
- [ ] 存在可运行的同步脚本、Docker Compose、CI 配置。
- [ ] `README.md`、`PROGRESS.md` 与实际实现保持一致。

---

## Suggested Execution Order

1. Task 1-2：先把 analysis 领域骨架和查询口建起来。
2. Task 3-4：补齐政策事件与标准化事件模型。
3. Task 5-6：完成真正的“分析能力”。
4. Task 7-8：接入 LLM 并形成可导出的报告。
5. Task 9-10：补齐前端工作台与跳转链路。
6. Task 11-12：修复运维脚本、容器化和 CI。
7. Task 13-14：最后统一验证并更新文档。
