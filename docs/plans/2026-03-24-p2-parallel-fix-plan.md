# P2 并行修复实施计划

> **For Codex:** 当前会话按 3 个并行子代理执行，每个子代理只处理自己负责的写入范围；主线程负责集成、复核与回归验证。

**Goal:** 修复当前审计确认的 P2 问题，保证热点页语义结构正确、前端兼容旧版接口响应、历史报告读时补全具备稳定的限流与降级行为。

**Architecture:** 本轮按“前端模板语义 / 前端兼容归一化 / 后端补全约束”三条独立子线拆分。每条子线都先补失败测试，再做最小修复，避免跨文件集冲突与无关重构。

**Tech Stack:** Vue 3、TypeScript、Vitest、FastAPI、SQLAlchemy、Pytest

---

## P2 范围确认

### P2-A：热点页存在无效 HTML 结构
- 现状：`frontend/src/views/HotNewsView.vue` 中候选股列表被渲染在 `<p>` / `<span>` 语义容器内，内部再嵌套 `<article>`，属于无效块级结构。
- 风险：浏览器会自动纠正 DOM，导致样式、可访问性、SSR/测试 DOM 结构与预期不一致。
- 修复原则：只调整模板结构与必要样式，不改变交互行为、路由行为和数据流。

### P2-B：`news.ts` 对旧响应缺少兼容层
- 现状：`frontend/src/api/news.ts` 直接把 `/api/news/hot` 与 `/api/news/impact-map` 响应当作新结构使用。
- 风险：旧缓存、历史后端实例或缺字段响应会让热点页的锚点事件切换、候选股增强字段展示出现空值分支不稳或运行时兼容问题。
- 修复原则：在 API 层做归一化，视图层继续消费稳定结构；不修改公共路由、不放大组件内部判空复杂度。

### P2-C：历史报告读时补全存在重复补全与预算测试缺口
- 现状：`backend/app/services/analysis_service.py` 对 `metadata_status = unavailable/domain_inferred` 的引用仍会持续进入 `_needs_web_source_enrichment(...)`。
- 风险：旧报告每次读取都可能重复触发补全逻辑；虽然上游缓存会降低外部请求，但服务层仍会重复遍历、重复调用补全入口，且缺少 `5 / 3 / 10` 预算上限测试。
- 修复原则：失败或域名推断后的引用应视为“已完成本轮读时降级”，再次读取优先使用已回写结果；同时补足预算边界测试。

---

## 子代理拆分

### 子代理 A：热点页模板语义修复

**写入范围**
- Modify: `frontend/src/views/HotNewsView.vue`
- Modify: `frontend/src/views/HotNewsView.test.ts`

**任务**
1. 写失败测试，证明候选股列表容器不应再挂在无效的 `<p>` 语义结构下。
2. 将候选股区域从段落内联结构改为语义正确的块级容器。
3. 保持现有按钮入口、锚点事件切换、候选证据展示行为不变。
4. 运行：`Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/views/HotNewsView.test.ts`

**完成标准**
- 不再出现 `<p>`/`<span>` 包裹 `<article>` 的结构。
- 热点页现有测试通过，且候选卡渲染行为保持不变。

### 子代理 B：`news.ts` 兼容归一化修复

**写入范围**
- Modify: `frontend/src/api/news.ts`
- Create or Modify: `frontend/src/api/news.test.ts`

**任务**
1. 写失败测试，覆盖旧 payload 缺少以下字段时仍能被安全消费：
   - `event_id` / `cluster_key` / `providers` / `source_coverage`
   - `anchor_event`
   - `source_breakdown` / `freshness_score` / `candidate_confidence` / `evidence_items`
2. 在 API 层新增归一化函数，对 `getHotNews(...)`、`getImpactMap(...)` 返回值补默认值。
3. 确保视图拿到的数组、字符串、数值字段始终稳定，避免把兼容逻辑扩散到视图。
4. 运行：`Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/api/news.test.ts`

**完成标准**
- 旧响应缺字段时，热点页仍能稳定拿到默认结构。
- 不改动 `HotNewsView.vue` 的业务接口签名。

### 子代理 C：历史报告补全重试约束与预算测试修复

**写入范围**
- Modify: `backend/app/services/analysis_service.py`
- Modify: `backend/tests/test_analysis_service.py`
- Modify: `backend/tests/test_analysis_routes.py`

**任务**
1. 写失败测试，覆盖：
   - `summary` 读取最多补 5 条 URL
   - `reports` 读取只处理前 3 份报告、每份最多 3 条、总上限 10 条
   - `metadata_status = unavailable/domain_inferred` 且降级字段齐全时，再次读取不重复进入补全
2. 以最小改动收紧 `_needs_web_source_enrichment(...)` 判定，避免失败降级后的旧报告在读路径重复补全。
3. 保持成功补全路径不变，`summary/reports` 继续返回 `200`。
4. 运行：
   - `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_service.py tests/test_analysis_routes.py`

**完成标准**
- 读时补全预算严格受 `5 / 3 / 10` 约束。
- 失败降级后的旧报告再次读取时优先使用回写结果，不重复补全。

---

## 主线程集成顺序

1. 先收子代理 A，确认前端模板结构修复不影响当前热点页交互。
2. 再收子代理 B，确认 API 兼容层与 A 的模板改动无冲突。
3. 最后收子代理 C，确认后端补全约束与测试闭环。
4. 集成后执行回归：
   - `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run test -- --run src/api/news.test.ts src/views/HotNewsView.test.ts src/views/AnalysisWorkbenchView.test.ts`
   - `Set-Location 'E:\Development\Project\StockProject\frontend'; npm run build`
   - `Set-Location 'E:\Development\Project\StockProject\backend'; uv run pytest -q tests/test_analysis_service.py tests/test_analysis_routes.py tests/test_web_source_metadata_service.py`

## 默认不做
- 不顺手处理无关样式优化。
- 不改动后端事件主链路接口。
- 不引入新的持久化字段或迁移。
- 不扩展到 Docker / CI / 导出能力。
