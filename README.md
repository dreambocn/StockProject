# StockProject

`StockProject` 是一个面向股票研究与事件驱动分析场景的全栈开源项目，提供从账户鉴权、行情与新闻采集，到事件影响映射、AI 分析工作台、关注列表自动化的完整链路。

当前仓库已经完成核心业务闭环，适合作为以下场景的基础工程：

- 股票研究与舆情分析产品原型
- FastAPI + Vue 3 前后端分离项目脚手架
- 带认证、安全风控、异步 Worker、AI 分析链路的示例工程

## 项目状态

- 当前状态：`Active`
- 最近进度：核心认证、股票数据、新闻事件、分析工作台、关注列表自动化已落地
- 详细里程碑：见 `PROGRESS.md`

## 核心特性

- 完整账户体系：注册、登录、刷新令牌、忘记密码、修改密码、当前用户信息、管理员用户管理。
- 安全防护到位：JWT 鉴权、密码哈希、刷新令牌全局撤销、登录验证码、邮箱验证码、IP 限流、CORS 白名单、请求级 `X-Request-ID` 日志追踪。
- 股票数据闭环：支持股票基础信息同步、最近交易日行情增量同步、个股详情、`daily/weekly/monthly` 周期行情查询与数据库优先回源策略。
- 新闻与事件沉淀：支持热点新闻、个股新闻、公告统一持久化，并提供历史事件查询与主题筛选能力。
- AI 分析工作台：支持事件锚点分析、流式生成、历史报告归档、结构化引用展示、联网来源元数据补全，以及 Markdown/HTML 导出。
- 候选股影响映射：支持热点主题到板块、受益方向、A 股候选股的动态关联、主题命中与证据增强展示。
- 关注列表自动化：支持关注股票管理、小时级资讯归档、交易日日报分析、后台 Worker 去重调度。
- 工程底座完善：引入 Alembic 统一管理数据库结构演进，新增 GitHub Actions CI 与环境矩阵文档。
- 后台任务中心：通过统一任务表 `system_job_runs` 聚合分析、新闻、自选、股票同步任务。
- 前端体验完整：包含首页、热点页、个股详情、分析工作台、关注页、后台管理页，并内置中英文国际化。

## 技术栈

- 前端：Vue 3、Vite、TypeScript、Pinia、Vue Router、Element Plus、VueUse Motion
- 后端：FastAPI、SQLAlchemy、Alembic、Redis、PostgreSQL、uv
- 数据源：Tushare、AkShare
- AI 能力：兼容 Responses 风格接口的大模型网关
- 测试：Pytest、Vitest

## 架构概览

```text
frontend/   Vue 3 Web 应用，负责交互、可视化与工作台体验
backend/    FastAPI 服务，负责鉴权、数据采集、事件分析与 API
docs/       文档目录（当前已清理阶段性计划）
PROGRESS.md 迭代进度记录
```

后端当前按领域拆分了 `auth`、`stocks`、`news`、`analysis`、`watchlist`、`admin`、`market_theme` 等模块；前端围绕 `dashboard`、`hot news`、`stock detail`、`analysis workbench`、`watchlist`、`admin` 等页面组织。

## 工程化文档

- 运行拓扑：`docs/architecture/runtime-topology.md`
- 环境矩阵：`docs/deploy/environment-matrix.md`
- 实施计划：`docs/plans/2026-03-30-stockproject-module-audit-and-next-steps.md`

## 功能模块

### 用户与权限

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/change-password`
- `POST /api/auth/reset-password`
- `GET /api/auth/me`
- `GET /api/admin/users`
- `POST /api/admin/users`

### 股票与行情

- `GET /api/stocks`
- `GET /api/stocks/{ts_code}`
- `GET /api/stocks/{ts_code}/daily`
- `POST /api/stocks/sync/full`
- `GET /api/admin/stocks`
- `POST /api/admin/stocks/full`

### 新闻、分析与自动化

- `GET /api/news/hot`
- `GET /api/news/events`
- `GET /api/news/impact-map`
- `GET /api/stocks/{ts_code}/news`
- `GET /api/stocks/{ts_code}/themes`
- `GET /api/analysis/stocks/{ts_code}/summary`
- `POST /api/analysis/stocks/{ts_code}/sessions`
- `GET /api/analysis/sessions/{session_id}/events`
- `GET /api/analysis/stocks/{ts_code}/reports`
- `GET /api/analysis/reports/{report_id}/export`
- `GET /api/admin/jobs`
- `GET /api/admin/jobs/summary`
- `GET /api/admin/jobs/{job_id}`
- `GET/POST/PATCH/DELETE /api/watchlist*`

## 快速开始

### 1. 准备依赖

- Python `3.14+`
- Node.js 与 npm
- PostgreSQL
- Redis

### 2. 安装依赖

在项目根目录执行：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv sync

Set-Location 'E:\Development\Project\StockProject\frontend'
npm install
```

### 3. 初始化环境变量

```powershell
Set-Location 'E:\Development\Project\StockProject'
Copy-Item '.\.env.example' '.\.env'
```

后端最少需要补齐以下配置：

- `POSTGRES_JDBC_URL`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `REDIS_JDBC_URL`
- `JWT_SECRET_KEY`

以下能力按需开启：

- `SMTP_*`：邮箱验证码与密码变更通知
- `TUSHARE_TOKEN`：股票基础库与行情同步
- `LLM_*`：分析工作台与 AI 报告生成
- `INIT_ADMIN_*`：首次启动自动创建管理员

完整示例请参考根目录 `.env.example`。

### 4. 先执行迁移（推荐）

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run alembic upgrade head
```

### 5. 一键启动开发环境

```powershell
Set-Location 'E:\Development\Project\StockProject'
.\start-dev.bat
```

该脚本会同时启动以下服务：

- Backend API：`http://127.0.0.1:8000`
- Watchlist Worker：关注列表定时任务
- Analysis Worker：分析会话队列处理
- Frontend Web：`http://127.0.0.1:5173`

如果只想检查路径与命令是否正确，可先执行：

```powershell
Set-Location 'E:\Development\Project\StockProject'
pwsh -File .\start-dev.ps1 -DryRun
```

## 单独运行

### 后端 API

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run fastapi dev main.py
```

### 前端 Web

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run dev
```

### 关注列表 Worker

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts/run_watchlist_worker.py
```

### 分析 Worker

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts/run_analysis_worker.py
```

### 手动同步股票主数据与最近交易日行情

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts/sync_stocks.py
```

## 测试与验证

### 后端测试

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q
```

### 前端测试

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run
```

### 前端构建

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run build
```

### 数据库结构自检

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run alembic upgrade head
uv run python -c "import asyncio; from app.db.migrations import validate_database_schema; from app.db.session import engine; asyncio.run(validate_database_schema(target_engine=engine)); print('schema validated')"
```

### CI 本地对齐

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run alembic upgrade head
uv run pytest -q

Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run
npm run build
```

## 目录结构

```text
StockProject/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ db/
│  │  ├─ integrations/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  └─ services/
│  ├─ scripts/
│  └─ tests/
├─ frontend/
│  ├─ src/
│  │  ├─ api/
│  │  ├─ i18n/
│  │  ├─ router/
│  │  ├─ stores/
│  │  └─ views/
│  └─ public/
├─ docs/
├─ PROGRESS.md
└─ README.md
```

## 适用场景

- 想快速搭建“行情 + 新闻 + AI 分析”一体化股票研究系统
- 想参考 Vue 3 + FastAPI + PostgreSQL + Redis 的前后端分层实践
- 想复用认证、安全风控、后台管理、异步 Worker、分析报告归档这类中后台能力

## Roadmap

- 增强主题与概念映射能力，例如补充更稳定的外部同步源与只读运营入口
- 增加更完整的研究成果交付能力，例如 PDF 导出与归档治理
- 持续补充部署、容器化与发布工程材料

## 贡献方式

欢迎通过 `Issue` 和 `Pull Request` 参与改进。提交前建议至少完成以下自检：

- 后端测试通过：`uv run pytest -q`
- 前端测试通过：`npm run test -- --run`
- 前端构建通过：`npm run build`
- 涉及行为变更时同步更新 `README.md` 或 `PROGRESS.md`

## License

本项目采用 `MIT License`。许可证全文见仓库根目录下的 `LICENSE` 文件。
