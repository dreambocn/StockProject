# StockProject 运行拓扑

## 本地四进程拓扑

本地开发默认同时运行四个进程：

1. **Backend API**
   - 命令：`uv run fastapi dev main.py`
   - 责任：对外提供鉴权、股票、新闻、分析、后台接口
2. **Analysis Worker**
   - 命令：`uv run python scripts/run_analysis_worker.py`
   - 责任：领取 `analysis_generation_sessions` 队列任务并产出分析报告
3. **Watchlist Worker**
   - 命令：`uv run python scripts/run_watchlist_worker.py`
   - 责任：执行自选股小时同步、每日报告、候选证据预刷新
4. **Frontend Web**
   - 命令：`npm run dev`
   - 责任：提供仪表盘、热点页、个股详情、分析工作台和后台页面

## 共享基础设施

- **PostgreSQL**
  - 持久化业务真相源
  - Alembic 统一管理结构演进
- **Redis**
  - 缓存、单飞锁、令牌与分析运行态辅助

## Schema 启动语义

- API / Analysis Worker / Watchlist Worker 三个 Python 入口统一调用 `ensure_database_schema()`
- `APP_ENV=development` 且 `DB_SCHEMA_BOOTSTRAP_MODE=auto_apply` 时：
  - 允许自动创建数据库
  - 允许自动创建 schema
  - 允许自动执行 Alembic 升级
- `DB_SCHEMA_BOOTSTRAP_MODE=validate_only` 时：
  - 只校验 `alembic_version`
  - 若数据库未迁移到最新版本，启动直接失败

## 统一任务平台

- 统一任务表：`system_job_runs`
- 统一状态：`queued | running | success | partial | failed`
- 第一版范围：
  - 统一记录
  - 后台查看
  - 条件筛选
  - 详情透视
- 第一版不做：
  - 人工取消
  - 人工重试
  - 手工补偿

## 分析与研究链路

- 热点/政策/个股新闻先沉淀到 `news_events`
- 分析任务写入 `analysis_generation_sessions`
- Worker 生成 `analysis_reports`
- 后台任务中心通过 `system_job_runs` 串起：
  - 分析生成
  - 新闻抓取
  - 自选小时同步
  - 自选日分析
  - 股票主数据全量同步
