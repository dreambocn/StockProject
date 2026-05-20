# StockProject AI 研究能力交付说明

更新时间：2026-05-20

## 已交付能力

- 研究计划预览：新增 `POST /api/analysis/stocks/{ts_code}/research-plan`，分析前生成研究摘要、证据范围、优先问题和预计步骤。
- 研究可追溯：`analysis_generation_sessions` 与 `analysis_reports` 持久化 `research_plan`，报告额外支持 `source_items` 统一来源列表。
- 来源工作区：前端在分析页合并结构化事件、政策原文、联网引用和行情数据，支持点击来源定位证据卡片。
- 报告交付：Markdown/HTML 导出包含研究计划、核心判断、关键证据、风险提示、来源列表和运行元数据；`format=package` 导出 HTML 研究包，内含 `report.md` 与 `source_manifest.json`。
- 评估集可用化：新增默认研究评估集、CLI、后台 API 和后台评估页，支持 `production_current` vs `evidence_first_v2` 对比。
- 演示 polish：分析页支持复制摘要、历史报告轻量差异提示；热点候选股首屏保留候选股票、置信度、来源覆盖和最强证据，详细证据默认折叠。

## 新增接口与命令

后端评估 API：

```powershell
GET  /api/admin/evaluations/datasets
GET  /api/admin/evaluations/runs
GET  /api/admin/evaluations/runs/{run_id}
POST /api/admin/evaluations/runs
```

后端 CLI：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python -m app.cli.evaluations import-default
uv run python -m app.cli.evaluations run --dataset default_research_cases --profiles production_current,evidence_first_v2
uv run python -m app.cli.evaluations summary --dataset default_research_cases
```

报告导出：

```powershell
GET /api/analysis/reports/{report_id}/export?format=markdown
GET /api/analysis/reports/{report_id}/export?format=html
GET /api/analysis/reports/{report_id}/export?format=package
```

## 兼容策略

- 评估集第一版使用 repo 内 JSON fixture 与本地运行结果文件，不新增数据库表。
- 旧报告没有 `research_plan` 或 `source_items` 时，导出和前端仍回退到旧字段渲染。
- 管理页仍沿用现有 `requiresAuth + requiresAdmin` 路由守卫。

## 验证命令

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_admin_evaluations_routes.py tests/test_evaluation_service.py tests/test_evaluation_cli.py tests/test_analysis_export_routes.py

Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/api/admin.test.ts src/views/AdminEvaluationsView.test.ts src/router/index.test.ts src/views/AdminConsoleView.test.ts src/views/AnalysisWorkbenchView.test.ts src/views/HotNewsView.test.ts src/api/analysis.ts
npm run build
```
