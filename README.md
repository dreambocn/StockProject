# StockProject 全栈项目

`StockProject` 是一个前后端分离的股票分析项目：

- `frontend/`：`Vue 3` + `Vite` + `TypeScript` + `Element Plus` + `VueUse Motion`
- `backend/`：`FastAPI`（使用 `uv` 管理）

## 已完成功能

### 后端能力

- 完成 Auth V1 全流程：注册、登录、刷新 Token、修改密码、登出、当前用户信息。
- 用户模型新增 `user_level`（`user/admin`），为权限路由与后台管理提供统一角色来源。
- 新增管理员能力：
  - `GET /api/admin/users` 查看用户列表（仅 admin）
  - `POST /api/admin/users` 创建用户并指定等级（仅 admin）
  - `POST /api/admin/stocks/full` 按状态触发股票主数据全量同步并入库（仅 admin）
  - `GET /api/admin/stocks` 提供后台股票主数据分页查询（仅 admin）
- 启动引导支持首个管理员自动创建（`INIT_ADMIN_*` 配置齐全且当前无 admin 时）。
- 登录支持用户名或邮箱（`account` 字段）。
- 接入 JWT 鉴权与密码哈希安全模块。
- 接入 Redis 刷新令牌存储。
- 支持登录失败自适应图形验证码：
  - 达到失败阈值后强制验证码
  - 提供验证码获取接口 `GET /api/auth/captcha`
  - 登录接口支持 `captcha_id` 与 `captcha_code`
- 新增邮箱验证码安全链路：
  - 注册前必须先获取并提交邮箱验证码
  - 修改密码前必须先获取并提交邮箱验证码（与当前密码双校验）
  - 修改密码成功后发送邮箱通知
  - 新增忘记密码重置流程（邮箱验证码 + 新密码）
- 强化会话安全：改密/重置密码成功后，服务端会撤销该用户所有已签发的 `refresh token`
  - 历史会话无法继续通过 `/api/auth/refresh` 获取新令牌
  - 已签发 `access token` 仍按原过期时间自然失效
- 新增 CORS 环境白名单控制：仅允许配置来源跨域，并在 `CORS_ALLOW_CREDENTIALS=true` 时禁止 `*` 通配。
- 新增发码接口 IP 风控：支持按场景分钟/天阈值限流，并在超限后写入临时黑名单。
- 升级健康检查为真实探针：
  - `GET /api/health/liveness` 提供进程级存活检查
  - `GET /api/health/readiness` 检查 PostgreSQL(`SELECT 1`)、Redis(`PING`) 与 SMTP 配置完整性
  - 返回 `ok | degraded | fail`，并包含按服务的 `status/latency_ms/error_type`
- 启动时支持自动检查/创建数据库、表与 schema（可配置）。
- 完成请求级日志能力（含 `X-Request-ID`）。
- 完成股票业务基础闭环（数据库存储 + 真实接口）：
  - 新增 `stock_instruments`、`stock_daily_snapshots`、`stock_kline_bars`、`stock_trade_calendars`、`stock_adj_factors`、`stock_sync_cursors` 六张表
  - 接入 Tushare 数据源并完整保留 `L/D/P/G` 股票基础库
  - 接入“最近 120 个交易日”增量行情同步
  - `/api/stocks` 支持关键词搜索（名称/代码/TS Code）与显式状态筛选，并对 `close/trade_date` 执行 DB-first 补全（snapshot -> daily kline -> Tushare）
  - `/api/stocks/{ts_code}` 提供股票详情与最新快照
  - `/api/stocks/{ts_code}/daily` 支持 `daily/weekly/monthly` 周期，先查库再回源并带 10 分钟缓存
  - `POST /api/stocks/sync/full` 支持登录态触发股票基础信息全量更新
 - 完成新闻持久化与分析查询能力：
   - 新增 `news_events` 表，统一持久化热点新闻与个股新闻（含公告）
   - `GET /api/news/hot` 与 `GET /api/stocks/{ts_code}/news` 已升级为 `Redis -> DB -> 上游` 链路，默认 1 小时刷新窗口
   - 新增 `GET /api/news/events`，支持按 `scope/ts_code/topic/时间范围/分页` 查询持久化新闻事件，便于 AI 直接分析
- 完成分析会话化能力：
  - 新增 `analysis_generation_sessions`、`analysis_reports` 归档增强、`analysis_event_links` 结果落库
  - `GET /api/analysis/stocks/{ts_code}/summary` 已收敛为只读最新快照接口
  - 新增 `POST /api/analysis/stocks/{ts_code}/sessions`、`GET /api/analysis/sessions/{session_id}/events`、`GET /api/analysis/stocks/{ts_code}/reports`
  - 支持活跃会话去重、新鲜报告缓存命中、Markdown 报告归档、流式增量输出
- 完成关注列表与自动归档基础设施：
  - 新增 `user_watchlist_items`、`stock_watch_snapshots` 两张表
  - 新增 `GET/POST/PATCH/DELETE /api/watchlist*` 接口
  - 新增独立 Worker 脚本 `uv run python scripts/run_watchlist_worker.py`
  - Worker 按“每小时 05 分资讯/快照归档 + 交易日 18:10 日报分析”执行股票级去重任务

### 前端能力

- 完成认证页面与流程：登录、注册、个人中心、修改密码。
- 新增重置密码页面（登录失败/忘记密码场景）。
- 接入路由守卫（`guestOnly` / `requiresAuth`）与登录后重定向。
- 新增 `requiresAdmin` 路由守卫，阻止普通用户进入后台页。
- 完成 Pinia 认证状态管理（含 token 持久化与会话恢复）。
- 新增后台管理页（统一终端风格）：用户列表 + 管理员创建用户表单。
- 新增后台管理中枢页：点击“后台管理”后统一进入功能分发页，再跳转到用户管理/股票管理。
- 新增后台股票管理页（统一终端风格）：
  - 管理员可按关键词与状态进行数据库分页查询
  - 新增“按参数获取全量”按钮与参数快捷键（ALL/L/D/P/G），触发服务端全量入库
  - 新增“默认查询”按钮，直接走数据库查询接口
- 完成密码确认与密码强度提示体验。
- 登录页支持验证码挑战展示与刷新。
- 注册页与修改密码页支持邮箱验证码发送、输入与倒计时。
- 完成 i18n 多语言基础：`zh-CN` 与 `en-US`，默认中文。
- 顶部语言切换支持本地持久化（`localStorage` 的 `app.locale`）。
- 认证相关错误信息已接入本地化映射（包含 422 校验错误首条提示）。
- 头部品牌区与语言切换器已升级为精致产品风：
  - 品牌文案：`AI STOCK LAB` / `by DreamBo`
  - 语言切换器采用胶囊分段样式
  - 已添加滑块式 active 背景动效
- 首页股票卡片已切换为后端真实数据，支持关键词搜索。
- 首页对缺失价格/日期的卡片增加轻量补全：仅补拉该股票最近一条 `daily` 数据并回填展示。
- 首页仪表盘股票区采用瀑布流布局，并在滚动到底部时自动加载下一页股票数据。
- 新增股票详情页（最新快照 + 最近 60 个交易日日线）。
- 分析工作台支持 Markdown 渲染、流式摘要更新、历史归档回看、联网增强开关与加入关注。
- 个股详情页新增加入/移出关注入口，并支持未登录跳转登录页。
- 新增关注页 `/watchlist`，支持查看关注股票、进入分析、移除关注与切换小时同步/每日分析/联网增强开关。

## 项目结构

### 前端关键文件

- `frontend/src/router/index.ts`：路由定义
- `frontend/src/router/guards.ts`：路由守卫
- `frontend/src/stores/auth.ts`：认证状态与 token 持久化
- `frontend/src/i18n/index.ts`：多语言初始化与切换
- `frontend/src/App.vue`：全局布局、头部品牌与语言切换

### 后端关键文件

- `backend/main.py`：开发入口（兼容 `fastapi dev main.py`）
- `backend/app/main.py`：FastAPI 应用装配
- `backend/app/api/routes/auth.py`：认证相关路由
- `backend/app/api/routes/admin.py`：后台管理路由（用户 + 股票，admin only）
- `backend/app/services/auth_service.py`：认证业务逻辑
- `backend/app/services/stock_sync_service.py`：股票增量同步服务
- `backend/app/services/captcha_service.py`：验证码服务
- `backend/app/core/security.py`：JWT 与密码安全
- `backend/app/core/settings.py`：环境配置解析
- `backend/app/integrations/tushare_gateway.py`：Tushare 数据网关
- `backend/app/services/watchlist_worker_service.py`：关注列表 Worker 去重、归档与日任务编排
- `backend/scripts/run_watchlist_worker.py`：关注列表定时 Worker 启动脚本

## 快速启动

### Windows 一键启动

在项目根目录执行：

```bash
start-dev.bat
```

该脚本会自动拉起后端与前端开发服务。
当前版本也会同时启动关注列表 Worker，便于本地直接验证小时资讯归档与每日报告任务。
若需要仅检查环境与路径而不实际拉起终端，可执行：`pwsh -File .\start-dev.ps1 -DryRun`

### 单独启动后端

后端配置文件：`backend/.env`（模板：`backend/.env.example`）。

```bash
cd backend
uv run fastapi dev main.py
```

默认地址：`http://127.0.0.1:8000`

常用登录安全参数（`backend/.env`）：

- `LOGIN_CAPTCHA_THRESHOLD`（默认 `2`）
- `LOGIN_FAIL_WINDOW_SECONDS`（默认 `900`）
- `CAPTCHA_TTL_SECONDS`（默认 `300`）
- `CAPTCHA_LENGTH`（默认 `4`）
- `EMAIL_CODE_TTL_SECONDS`（默认 `300`）
- `EMAIL_CODE_COOLDOWN_SECONDS`（默认 `60`）
- `EMAIL_CODE_LENGTH`（默认 `6`）
- `EMAIL_CODE_IP_LIMIT_PER_MINUTE`（默认 `10`）
- `EMAIL_CODE_IP_LIMIT_PER_DAY`（默认 `200`）
- `EMAIL_CODE_IP_BLOCK_SECONDS`（默认 `900`）
- `INIT_ADMIN_USERNAME`（可选；与下方两项同时配置才生效）
- `INIT_ADMIN_EMAIL`（可选）
- `INIT_ADMIN_PASSWORD`（可选）
- `TRUST_PROXY_HEADERS`（默认 `false`；仅在受信代理部署场景开启）
- `TRUSTED_PROXY_IPS`（逗号分隔受信代理 IP；仅在 `TRUST_PROXY_HEADERS=true` 时生效）
- `CORS_ALLOW_ORIGINS`（逗号分隔白名单，例如 `http://localhost:5173,https://app.example.com`）
- `CORS_ALLOW_CREDENTIALS`（默认 `true`；当为 `true` 时禁止在白名单中使用 `*`）
- `CORS_ALLOW_ORIGIN_REGEX`（默认放行 `localhost/127.0.0.1` 任意端口，避免 Vite 端口漂移导致预检失败）
- `TUSHARE_TOKEN`（Tushare Pro token，用于行情同步）
- `LLM_BASE_URL`（大模型网关基地址，默认 `https://aixj.vip`）
- `LLM_WIRE_API`（模型接口类型，当前使用 `responses`）
- `LLM_API_KEY`（大模型访问密钥，敏感信息，仅放本地 `.env`）
- `LLM_MODEL`（默认模型，当前为 `gpt-5.1-codex-mini`）
- `LLM_REASONING_EFFORT`（默认推理强度，当前为 `high`）
- `LLM_STREAM_ENABLED`（是否启用流式输出，默认 `true`）
- `LLM_WEB_SEARCH_ENABLED`（是否允许联网搜索增强，默认 `false`）
- `ANALYSIS_ACTIVE_SESSION_TTL_SECONDS`（活跃分析会话去重 TTL，默认 `300`）
- `ANALYSIS_REPORT_FRESHNESS_MINUTES`（分析报告冷却窗口，默认 `60`；1 小时内复用最近归档，不重复触发分析）
- `WEB_SOURCE_METADATA_TIMEOUT_SECONDS`（联网引用元数据抓取超时秒数，默认 `3`）
- `WEB_SOURCE_METADATA_CACHE_TTL_SECONDS`（联网引用元数据成功缓存秒数，默认 `86400`）
- `WEB_SOURCE_METADATA_FAILURE_TTL_SECONDS`（联网引用元数据失败缓存秒数，默认 `7200`）
- `WEB_SOURCE_METADATA_MAX_BYTES`（联网引用元数据抓取最大读取字节数，默认 `524288`）
- `STOCK_SYNC_TRADE_DAYS`（增量同步交易日窗口，默认 `120`）
- `STOCK_DAILY_CACHE_TTL_SECONDS`（股票日线缓存秒数，默认 `600`）
- `STOCK_TRADE_CAL_CACHE_TTL_SECONDS`（交易日历缓存秒数，默认 `86400`）
- `STOCK_ADJ_FACTOR_CACHE_TTL_SECONDS`（复权因子缓存秒数，默认 `3600`）
- `STOCK_RELATED_NEWS_CACHE_TTL_SECONDS`（个股新闻缓存秒数，默认 `3600`）
- `HOT_NEWS_CACHE_TTL_SECONDS`（热点新闻缓存秒数，默认 `3600`）

邮件服务参数（`backend/.env`）：

- `SMTP_HOST`
- `SMTP_PORT`（默认 `465`）
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`（可选，不填则使用 `SMTP_USERNAME`）
- `SMTP_USE_SSL`（默认 `true`）

### 单独启动前端

先根据 `frontend/.env.example` 创建 `frontend/.env`，然后执行：

```bash
cd frontend
npm run dev
```

默认地址：`http://127.0.0.1:5173`

### 同步最近 120 个交易日股票数据（后端内部命令）

```bash
cd backend
uv run python scripts/sync_stocks.py
```

说明：

- 该命令会同步上市股票主数据与最近 N 个交易日（默认 `120`）行情快照。
- 股票基础信息按 `L/D/P/G` 全状态同步并落库，行情仍按最近 N 个交易日增量拉取。
- `N` 可通过 `STOCK_SYNC_TRADE_DAYS` 配置调整。

### 启动关注列表 Worker

```bash
cd backend
uv run python scripts/run_watchlist_worker.py
```

说明：

- Worker 默认轮询当前时间，每小时 `05` 分执行关注股票资讯/快照归档。
- Worker 默认在 `Asia/Hong_Kong` 时区的交易日 `18:10` 执行关注股票日报分析。
- 同一股票在同一轮任务中只会执行一次，避免多人关注导致重复调用 AI。

## Auth API 列表

- `POST /api/auth/register`
- `POST /api/auth/register/email-code`
- `POST /api/auth/login`（`account` 支持用户名或邮箱）
- `GET /api/auth/captcha`
- `POST /api/auth/refresh`
- `POST /api/auth/change-password`
- `POST /api/auth/change-password/email-code`
- `POST /api/auth/reset-password/email-code`
- `POST /api/auth/reset-password`
- `POST /api/auth/logout`
- `GET /api/auth/me`

## Admin API 列表

- `GET /api/admin/users`（需 admin）
- `POST /api/admin/users`（需 admin）
- `POST /api/admin/stocks/full`（需 admin；支持 `list_status`，默认 `ALL`；执行全量同步并入库）
- `GET /api/admin/stocks`（需 admin；支持 `keyword/list_status/page/page_size`，默认分页 `page=1&page_size=20`）

## Health API 列表

- `GET /api/health/liveness`
- `GET /api/health/readiness`
- `GET /api/health`（兼容入口，语义等同于 readiness）

## Stock API 列表

- `GET /api/stocks`（支持 `keyword/list_status/page/page_size`，默认 `list_status=L`，可显式传 `ALL` 或 `L,D,P,G`）
- `GET /api/stocks/{ts_code}`
- `GET /api/stocks/{ts_code}/daily`（支持 `limit/period/trade_date/start_date/end_date`，`period` 可选 `daily|weekly|monthly`）
- `GET /api/stocks/{ts_code}/news`（支持 `limit/include_announcements`；默认 1 小时窗口内优先走缓存/数据库）
- `GET /api/stocks/trade-cal`（支持 `exchange/start_date/end_date/is_open`，先查库再回源）
- `GET /api/stocks/{ts_code}/adj-factor`（支持 `limit/trade_date/start_date/end_date`，先查库再回源）
- `POST /api/stocks/sync/full`（需登录态，用于触发股票基础信息全量更新）

## News API 列表

- `GET /api/news/hot`（支持 `limit/topic`；默认 1 小时窗口内优先走缓存/数据库）
- `GET /api/news/hot` 现返回 `event_id/cluster_key/providers/source_coverage`
- `GET /api/news/impact-map`（支持 `topic/candidate_limit`；返回 `anchor_event` 与候选股相关度信息）
- `GET /api/news/events`（支持 `scope/ts_code/topic/published_from/published_to/page/page_size`；直接查询持久化新闻事件）

## Analysis API 列表

- `GET /api/analysis/stocks/{ts_code}/summary`（支持 `topic/event_id`）
- `POST /api/analysis/stocks/{ts_code}/sessions`
- `POST /api/analysis/stocks/{ts_code}/sessions` 支持 `event_id/use_web_search`
- `GET /api/analysis/sessions/{session_id}/events`
- `GET /api/analysis/stocks/{ts_code}/reports`（支持 `topic/event_id`）
- 分析报告中的 `web_sources` 现会解析并返回结构化引用（`title/url/source/published_at/snippet`）
- 热点页会在本地持久化每个 topic 的锚点事件选择，刷新后继续沿用
- 服务端会对 `web_sources.url` 做最佳努力元数据补全，额外返回 `domain/metadata_status`，并在分析页分开展示“结构化来源”和“联网引用”

## Watchlist API 列表

- `GET /api/watchlist`（需登录）
- `POST /api/watchlist/items`（需登录）
- `PATCH /api/watchlist/items/{ts_code}`（需登录）
- `DELETE /api/watchlist/items/{ts_code}`（需登录）
- `GET /api/watchlist/feed`（需登录）

认证安全语义（重要）：

- `POST /api/auth/change-password` 成功后，会全量撤销该用户历史 `refresh token`
- `POST /api/auth/reset-password` 成功后，会全量撤销该用户历史 `refresh token`
- 上述场景下，旧 `refresh token` 调用 `POST /api/auth/refresh` 会返回 `401`

## 测试与构建

后端测试：

```bash
cd backend
uv run pytest -q
```

前端测试：

```bash
cd frontend
npm run test -- --run
```

前端构建：

```bash
cd frontend
npm run build
```
