# StockProject 工程化落地变动清单（2026-03-31）

## 1. 变更概览

- 本次落地覆盖四个方向：
  - 工程底座：Alembic、运行时模式治理、启动脚本、环境文档、CI
  - 统一任务平台：统一任务表、任务服务、后台任务中心 API 与页面
  - 分析治理与导出：运行元数据、Markdown/HTML 导出、工作台联动
  - 研究域扩展：主题域模型、主题查询接口、热点/个股前端展示
- 当前代码已经完成前后端联动与回归验证，适合按“单个主提交”收口。

## 2. 建议提交信息

### 2.1 推荐单提交标题

`feat: 完成工程化基座、统一任务中心与分析治理落地`

### 2.2 推荐提交正文

```text
- 引入 Alembic 与运行时模式治理，补齐启动脚本、环境矩阵与 GitHub Actions CI
- 落地 system_job_runs 统一任务平台，并接入分析、新闻、自选与股票同步任务
- 增加后台任务中心 API 与前端页面，支持任务汇总、筛选、详情查看
- 增加分析运行元数据治理与 Markdown/HTML 导出能力
- 新增市场主题域模型与前后端展示链路，补齐相关回归测试
```

### 2.3 可选拆分方案

- 提交一：`feat: 引入 Alembic 与运行时模式治理`
- 提交二：`feat: 落地统一任务平台与后台任务中心`
- 提交三：`feat: 增加分析导出与市场主题域能力`

> 如果不准备手工拆分历史，建议直接使用“2.1 + 2.2”的单提交方案，当前改动耦合度更高，也更贴近这次实施计划的整体交付语义。

## 3. 后端变更清单

### 3.1 工程底座与迁移治理

- 新增 Alembic 基础设施：
  - `backend/alembic.ini`
  - `backend/alembic/env.py`
  - `backend/alembic/script.py.mako`
  - `backend/alembic/versions/20260331_0001_baseline_current_schema.py`
  - `backend/alembic/versions/20260331_0002_system_job_runs.py`
  - `backend/alembic/versions/20260331_0003_analysis_runtime_metadata.py`
  - `backend/alembic/versions/20260331_0004_market_themes.py`
- 新增迁移辅助：
  - `backend/app/db/migrations.py`
- 调整运行时与初始化逻辑：
  - `backend/app/core/settings.py`
  - `backend/app/db/init_db.py`
  - `backend/app/main.py`
- 关键落地：
  - 新增 `APP_ENV`、`DB_SCHEMA_BOOTSTRAP_MODE`、`INIT_ADMIN_ENABLED`
  - 启动期区分 `auto_apply` 与 `validate_only`
  - Worker/API 共用同一套 schema 判断
  - 兼容“旧库已有表但无 alembic 版本表”的 baseline 升级路径

### 3.2 统一任务平台

- 新增统一任务领域对象：
  - `backend/app/models/system_job_run.py`
  - `backend/app/schemas/admin_jobs.py`
  - `backend/app/services/job_service.py`
  - `backend/app/services/job_query_service.py`
- 改造关联模型：
  - `backend/app/models/analysis_generation_session.py`
  - `backend/app/models/news_fetch_batch.py`
  - `backend/app/models/__init__.py`
- 接入任务生命周期的业务服务：
  - `backend/app/services/analysis_service.py`
  - `backend/app/services/analysis_repository.py`
  - `backend/app/services/news_fetch_batch_service.py`
  - `backend/app/services/watchlist_worker_service.py`
  - `backend/app/services/stock_sync_service.py`
- 新增后台接口：
  - `backend/app/api/routes/admin.py`
- 关键落地：
  - 新增 `system_job_runs`
  - 统一记录 `analysis_generate`、`news_fetch`、`watchlist_hourly_sync`、`watchlist_daily_analysis`、`stock_sync_full`
  - 支持任务分页、筛选、汇总、详情查看

### 3.3 分析治理与导出

- 新增分析治理与导出服务：
  - `backend/app/services/analysis_prompt_registry.py`
  - `backend/app/services/analysis_export_service.py`
- 调整分析相关模型/接口：
  - `backend/app/models/analysis_generation_session.py`
  - `backend/app/models/analysis_report.py`
  - `backend/app/schemas/analysis.py`
  - `backend/app/api/routes/analysis.py`
- 调整分析生成与 LLM 兼容逻辑：
  - `backend/app/services/analysis_service.py`
  - `backend/app/services/llm_analysis_service.py`
  - `backend/app/services/llm_client_service.py`
- 关键落地：
  - 持久化 `prompt_version`、`model_name`、`reasoning_effort`
  - 持久化 `token_usage_input`、`token_usage_output`、`cost_estimate`、`failure_type`
  - 新增 `GET /api/analysis/reports/{report_id}/export?format=markdown|html`
  - 修复流式回调兼容与降级元数据兼容

### 3.4 研究域扩展

- 新增主题域模型/服务：
  - `backend/app/models/market_theme.py`
  - `backend/app/models/market_theme_membership.py`
  - `backend/app/models/market_theme_sync_batch.py`
  - `backend/app/services/market_theme_service.py`
- 扩展接口与 schema：
  - `backend/app/api/routes/stocks.py`
  - `backend/app/api/routes/news.py`
  - `backend/app/schemas/stocks.py`
  - `backend/app/schemas/news.py`
- 关键落地：
  - 新增 `GET /api/stocks/{ts_code}/themes`
  - `GET /api/news/impact-map` 候选股补充 `theme_matches`、`theme_evidence`

### 3.5 基础设施与文档

- 新增/更新：
  - `.env.example`
  - `.github/workflows/ci.yml`
  - `docs/deploy/environment-matrix.md`
  - `docs/architecture/runtime-topology.md`
  - `README.md`
  - `PROGRESS.md`
  - `start-dev.ps1`
  - `backend/pyproject.toml`
  - `backend/uv.lock`

## 4. 前端变更清单

### 4.1 后台任务中心

- 新增：
  - `frontend/src/views/AdminJobsView.vue`
  - `frontend/src/views/AdminJobsView.test.ts`
- 调整：
  - `frontend/src/api/admin.ts`
  - `frontend/src/api/admin.test.ts`
  - `frontend/src/router/index.ts`
  - `frontend/src/views/AdminConsoleView.vue`
  - `frontend/src/views/AdminConsoleView.test.ts`
- 关键落地：
  - 新增 `/admin/jobs`
  - 新增任务汇总卡片、筛选区、分页表格、详情面板
  - 后台首页增加“任务中心”入口

### 4.2 分析工作台

- 调整：
  - `frontend/src/api/analysis.ts`
  - `frontend/src/views/AnalysisWorkbenchView.vue`
  - `frontend/src/views/AnalysisWorkbenchView.test.ts`
  - `frontend/src/views/AnalysisWorkbenchExport.test.ts`
- 关键落地：
  - 新增导出 Markdown / HTML 按钮
  - 展示分析运行元数据
  - 同步修正工具栏按钮顺序与断言

### 4.3 个股与热点主题增强

- 调整：
  - `frontend/src/api/stocks.ts`
  - `frontend/src/api/news.ts`
  - `frontend/src/views/StockDetailView.vue`
  - `frontend/src/views/StockDetailView.test.ts`
  - `frontend/src/views/HotNewsView.vue`
  - `frontend/src/views/HotNewsView.test.ts`
- 关键落地：
  - 个股详情新增主题区块
  - 热点候选卡补充主题命中与证据表达

### 4.4 语言包与导航联动

- 调整：
  - `frontend/src/i18n/locales/zh-CN.ts`
  - `frontend/src/i18n/locales/en-US.ts`
  - `frontend/src/router/index.ts`

## 5. 测试与验证清单

### 5.1 后端

- 已通过：
  - `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q`
  - 结果：`267 passed`
- 重点补充：
  - `tests/test_schema_bootstrap_mode.py`
  - `tests/test_settings_runtime_modes.py`
  - `tests/test_alembic_baseline_smoke.py`
  - `tests/test_system_job_model.py`
  - `tests/test_job_service.py`
  - `tests/test_admin_jobs_routes.py`
  - `tests/test_analysis_export_routes.py`
  - `tests/test_analysis_job_integration.py`
  - `tests/test_news_fetch_job_integration.py`
  - `tests/test_watchlist_job_integration.py`
  - `tests/test_stock_sync_job_integration.py`
  - `tests/test_market_theme_routes.py`

### 5.2 前端

- 已通过：
  - `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run`
  - 结果：`89 passed`
- 已通过构建：
  - `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run build`

### 5.3 迁移命令

- 已通过真实命令验证：
  - `Set-Location 'E:\Development\Project\StockProject\backend'; uv run alembic upgrade head`

## 6. 提交前检查建议

- 建议优先确认本次提交包含以下目录：
  - `backend/alembic/`
  - `backend/app/`
  - `backend/tests/`
  - `frontend/src/`
  - `docs/`
  - `.github/workflows/ci.yml`
  - `.env.example`
  - `README.md`
  - `PROGRESS.md`
  - `start-dev.ps1`
- 如准备一次性提交，建议提交前复核：
  - 是否包含新建文档与 CI 文件
  - 是否遗漏 Alembic revision 文件
  - 是否遗漏前端新页面 `AdminJobsView`
  - 是否遗漏新增测试文件
