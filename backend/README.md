# StockProject 后端

这是 `StockProject` 的 FastAPI 后端服务，负责鉴权、股票数据、新闻事件、政策文档、AI 分析、关注列表和后台任务。依赖使用 `uv` 管理，默认从仓库根目录 `.env` 读取运行配置。

## 常用命令

安装依赖：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv sync
```

启动开发 API：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run fastapi dev main.py
```

运行全部测试：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q
```

运行单个测试文件或用例：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_auth_routes.py
uv run pytest -q tests/test_auth_routes.py::test_login_supports_username_or_email
```

执行数据库迁移和结构校验：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run alembic upgrade head
uv run python -c "import asyncio; from app.db.migrations import validate_database_schema; from app.db.session import engine; asyncio.run(validate_database_schema(target_engine=engine)); print('schema validated')"
```

## 主要目录

- `app/api/`：FastAPI 路由与依赖，按 `auth`、`stocks`、`news`、`policy`、`analysis`、`watchlist`、`admin` 拆分。
- `app/services/`：业务服务层，承载缓存、同步、分析编排、新闻映射、政策同步和 Worker 主逻辑。
- `app/models/`：SQLAlchemy ORM 模型。
- `app/schemas/`：Pydantic 请求与响应模型。
- `app/db/`：数据库连接、初始化、迁移校验与 schema bootstrap。
- `app/integrations/`：AkShare、Tushare、官方政策源等外部集成。
- `scripts/`：可单独运行的同步脚本和 Worker 入口。
- `tests/`：后端单元测试和集成测试。

## 关键配置

最少需要关注这些环境变量，示例见仓库根目录 `.env.example`：

- `POSTGRES_JDBC_URL`、`POSTGRES_USER`、`POSTGRES_PASSWORD`：PostgreSQL 连接配置。
- `REDIS_JDBC_URL`、`REDIS_USERNAME`、`REDIS_PASSWORD`：Redis 缓存与鉴权状态配置。
- `JWT_SECRET_KEY`：JWT 签名密钥，开发外环境必须替换默认值。
- `TUSHARE_TOKEN`：股票基础库、行情、新闻等 Tushare 能力。
- `LLM_*`：分析工作台的大模型网关、模型、流式和联网检索配置。
- `SMTP_*`：邮箱验证码和密码变更通知。
- `DB_SCHEMA_BOOTSTRAP_MODE`：开发环境可用 `auto_apply`，部署环境建议使用 `validate_only` 配合 Alembic。

## 后台任务

关注列表 Worker：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts/run_watchlist_worker.py
```

分析 Worker：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts/run_analysis_worker.py
```

手动同步股票主数据：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts/sync_stocks.py
```

手动同步政策文档：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts/sync_policy_documents.py
```

## 排障入口

- 健康检查：`Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health/readiness'`
- API 入口：`backend/main.py` 与 `backend/app/main.py`
- 配置来源：`backend/app/core/settings.py`
- 数据库连接：`backend/app/db/session.py`
- 任务状态：`GET /api/admin/jobs` 与 `system_job_runs` 表
- 热点影响面板：`backend/app/services/news_impact_service.py`
- 分析会话：`backend/app/services/analysis_service.py` 与 `backend/app/services/analysis_runtime_service.py`
