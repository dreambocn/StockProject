# StockProject 分析链路审查问题完整修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复代码审查中发现的分析链路稳定性、尾延迟、缓存锁回收和文档交接问题，重点保证分析 Worker 不重复领取、日报状态不误报完成、分析读写路径可控。

**Architecture:** 以当前后端服务层为主线做最小行为变更：保留既有 HTTP API、响应字段和分析模式，优先在 repository/service/helper 层补稳定性能力。第一组问题已经在当前仓库有实现痕迹，本计划将其作为回归基线；新增重点落在 Worker heartbeat、自选日报终态语义、归档批量加载、SSE 数据库兜底和价格窗口批量化。

**Tech Stack:** FastAPI、async SQLAlchemy、PostgreSQL/SQLite 测试库、Redis 缓存、OpenAI-compatible LLM client、Vue 3 + Vite + Vitest。

---

## Summary

本计划覆盖 10 个 review findings，按优先级分三批实施。

- 第一批回归锁定 Finding 1-5：流式 LLM 降级、Web 来源有限并发补全、单飞锁回收、分析锁回收、前后端 README 补齐。
- 第二批修复 P1 新问题 Finding 6-7：分析 Worker stale 误重领、自选股日分析提前标记完成。
- 第三批修复 P2 性能与长连接问题 Finding 8-10：分析归档 N+1、SSE 无心跳兜底、事件价格窗口逐条补全。

## Baseline: Findings 1-5 回归锁定

这些问题在当前代码中已经看到实现和测试痕迹，实施时先跑 focused 回归，只有失败才做小范围补丁。

- [ ] 确认 `stream_llm_text(use_web_search=True)` 遇到 `web_search/tool/unsupported` 异常时，会降级调用普通请求并 yield 完整文本。
- [ ] 确认 `enrich_web_sources()` 对未缓存 URL 使用 `asyncio.Semaphore` 做有限并发，默认并发上限保持为 3，输出顺序不变。
- [ ] 确认 `stock_cache_service.singleflight_lock()` 和 `analysis_runtime_service.session_lock()` 在上下文退出后清理空闲 key。
- [ ] 确认 `backend/README.md` 与 `frontend/README.md` 已替换模板内容，命令均使用 Windows PowerShell 写法。
- [ ] 回归命令：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_llm_client_service.py tests/test_web_source_metadata_service.py tests/test_stock_cache_service.py tests/test_analysis_runtime_service.py
```

## Batch 1: P1 稳定性修复

### Task 1: 修复分析 Worker stale 误重领

**Files:**
- Modify: `backend/app/services/analysis_repository.py`
- Modify: `backend/app/services/analysis_service.py`
- Test: `backend/tests/test_analysis_repository.py`
- Test: `backend/tests/test_analysis_service.py`

- [ ] 在 `claim_next_analysis_session_for_worker()` 领取 queued/running 时显式写入 `heartbeat_at=now` 与 `updated_at=now`，避免依赖 ORM `onupdate` 的隐式行为。
- [ ] stale running 判断改为优先使用 `heartbeat_at`：`heartbeat_at < stale_before OR (heartbeat_at IS NULL AND updated_at < stale_before)`。
- [ ] 在 `analysis_service.py` 新增内部 heartbeat helper，使用独立 `SessionLocal` 周期刷新 `AnalysisGenerationSession.heartbeat_at`、`updated_at` 和关联 `SystemJobRun.heartbeat_at`。
- [ ] 在 `run_analysis_session_by_id()` 进入 running 后启动 heartbeat task，默认间隔 30 秒；正常完成、异常失败或取消时都必须停止该 task。
- [ ] 在 functional multi-agent 的角色事件回调里保留当前进度写入，同时不依赖角色事件作为唯一 heartbeat 来源。
- [ ] 新增测试：queued 被领取后 `heartbeat_at` 不为空；running 会话 heartbeat 新鲜但 updated_at 很旧时不会被 stale 回收；heartbeat 过期时才允许回收。
- [ ] 新增测试：模拟长时间 Agent 调用时 heartbeat helper 至少刷新一次；执行结束后 heartbeat task 被取消。

### Task 2: 修复自选日报提前完成

**Files:**
- Modify: `backend/app/services/watchlist_worker_service.py`
- Test: `backend/tests/test_watchlist_worker_service.py`
- Test: `backend/tests/test_watchlist_job_integration.py`

- [ ] 在 `run_daily_watchlist_analysis()` 中新增终态判断：只有 `analysis_result["cached"] is True`、或 `analysis_result["status"] == "completed"`、或存在可用 `report_id` 时，才调用 `mark_daily_analysis_completed()`。
- [ ] 当 `analysis_result["reused"] is True` 且状态为 `queued` 或 `running` 时，不更新 `last_daily_analysis_at`。
- [ ] 复用运行中会话时，将 `watchlist_daily_analysis` job 标记为 `partial`，`summary` 使用中文说明“已挂接运行中的分析会话”，`metrics_json` 写入 `waiting_for_session=true`、`session_id`、`status`、`cached=false`、`reused=true`。
- [ ] 保持单只股票失败不影响后续标的的现有降级语义。
- [ ] 新增测试：复用 running session 不写 `last_daily_analysis_at`，job 为 `partial`。
- [ ] 新增测试：命中缓存或 completed 结果仍写 `last_daily_analysis_at`，job 为 `success`。

## Batch 2: P2 读路径与长连接优化

### Task 3: 修复分析归档 N+1 查询

**Files:**
- Modify: `backend/app/services/analysis_repository.py`
- Modify: `backend/app/services/analysis_service.py`
- Test: `backend/tests/test_analysis_service.py`
- Test: `backend/tests/test_analysis_repository.py`

- [ ] 新增 `list_analysis_agent_runs_for_reports(session, report_ids)`，一次查出多份报告的 agent runs，并按 `report_id -> list[AnalysisAgentRun]` 分组。
- [ ] `list_stock_analysis_report_archives()` 改为批量加载 role rows，不再每个 report 单独调用 `list_analysis_agent_runs_for_report()`。
- [ ] 归档列表优先使用 `report.evidence_events` 内联证据；对没有内联证据的老报告，归档列表允许返回空证据或有限摘要，不在列表接口逐条 fallback 查询。
- [ ] `/reports/{report_id}/evidence` 继续保留完整 fallback 查询，保证老数据查看证据不丢能力。
- [ ] 新增测试：归档列表对 10 份报告只调用一次批量 roles 查询；内联证据存在时不触发 fallback 证据查询。
- [ ] 新增测试：老报告无内联证据时，证据详情接口仍能通过 fallback 返回事件。

### Task 4: 为 SSE 增加心跳和数据库终态兜底

**Files:**
- Modify: `backend/app/api/routes/analysis.py`
- Test: `backend/tests/test_analysis_routes.py`

- [ ] 在 SSE `event_stream()` 中使用 `asyncio.wait_for(queue.get(), timeout=15)`。
- [ ] 超时后用当前请求注入的 `AsyncSession` 重新读取 `AnalysisGenerationSession`；必要时先 `expire` 或重新查询，避免复用旧对象。
- [ ] 每次超时读取后发送 `status` 事件，payload 至少包含 `session_id`、`status`、`current_stage`、`stage_message`、`heartbeat_at`、`report_id`。
- [ ] 若数据库状态为 `completed`，发送 `completed` 事件并结束流；若为 `failed`，发送 `error` 事件并结束流。
- [ ] 保持现有事件名和前端处理方式不变，不新增前端必需字段。
- [ ] 新增测试：没有 event_bus 消息时，SSE 会输出周期性 `status`。
- [ ] 新增测试：订阅建立后数据库状态变为 completed/failed 时，SSE 能靠兜底查询结束。

## Batch 3: P2 分析生成尾延迟优化

### Task 5: 批量加载事件价格窗口

**Files:**
- Modify: `backend/app/services/stock_quote_service.py`
- Modify: `backend/app/services/analysis_service.py`
- Test: `backend/tests/test_stock_quote_service.py`
- Test: `backend/tests/test_analysis_service.py`

- [ ] 新增 `load_price_windows_with_completion(session, ts_code, anchor_dates, window_size=5, fetch_daily_by_range_fn=None)`。
- [ ] 对 `anchor_dates` 去重后计算整体日期范围：最早 anchor date 到最晚 anchor date + 30 天。
- [ ] 一次查询 `StockDailySnapshot` 和 `StockKlineBar` 覆盖整体范围，并在内存中为每个 anchor date 切出从该日期开始的前向 5 条窗口。
- [ ] 若本地数据不足且有 Tushare token，则只发一次合并 range 请求并回写 `stock_kline_bars`，再重新读取本地 kline 后切窗口。
- [ ] 无 token 或远端失败时，按现有降级语义返回已有本地窗口，不抛错阻断分析。
- [ ] `run_analysis_session_by_id()` 在事件循环前批量调用新 helper，循环内通过 `price_windows_by_date.get(anchor_date)` 取窗口。
- [ ] 保持 `load_price_window_with_completion()` 兼容入口不删除；可内部委托到新批量函数，避免现有测试和调用方破坏。
- [ ] 新增测试：多个 anchor date 只触发一次远端 fetch；返回窗口与原单条逻辑一致。
- [ ] 新增测试：分析生成处理 30 个事件时不会逐条调用旧 helper。

## Full Verification

后端 focused 回归：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_llm_client_service.py tests/test_web_source_metadata_service.py tests/test_stock_cache_service.py tests/test_analysis_runtime_service.py
uv run pytest -q tests/test_analysis_repository.py tests/test_analysis_service.py tests/test_analysis_routes.py tests/test_watchlist_worker_service.py tests/test_watchlist_job_integration.py tests/test_stock_quote_service.py
```

后端全量回归：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q
```

前端回归：

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run
npm run build
```

仓库状态检查：

```powershell
Set-Location 'E:\Development\Project\StockProject'
git status --short
git diff --check
```

## Assumptions

- 以 2026-04-29 当前仓库状态为基线，Finding 1-5 已有实现，除非测试失败，不做重复重构。
- 本轮不新增数据库迁移；现有 `heartbeat_at`、`updated_at`、`evidence_events`、`analysis_agent_runs` 足够支撑修复。
- heartbeat 周期默认 30 秒，SSE 数据库兜底超时默认 15 秒，先写为模块常量，不新增环境变量。
- 自选日报复用运行中分析会话时，优先保证“不误报完成”；是否在会话完成后自动回填 `last_daily_analysis_at` 留作后续独立优化。
- 价格窗口批量化只改变取数方式，不改变因子权重、事件筛选、报告结构和 HTTP 响应字段。
