# P0 计划书 3：前端分析工作台与联动展示

## 目标
- 提供公开只读的分析工作台页面。
- 从热点新闻与个股详情两处进入分析页。
- 在后端返回 `pending / partial` 时提供清晰降级展示。

## 写入范围
- `frontend/src/api/analysis.ts`
- `frontend/src/views/AnalysisWorkbenchView.vue`
- `frontend/src/router/index.ts`
- `frontend/src/App.vue`
- `frontend/src/i18n/locales/zh-CN.ts`
- `frontend/src/i18n/locales/en-US.ts`
- `frontend/src/views/HotNewsView.vue`
- `frontend/src/views/StockDetailView.vue`
- `frontend/src/views/AnalysisWorkbenchView.test.ts`
- `frontend/src/router/index.test.ts`
- `frontend/src/App.test.ts`
- `frontend/src/views/HotNewsView.test.ts`
- `frontend/src/views/StockDetailView.test.ts`

## 页面能力
- 新增公开路由 `/analysis`，路由名 `analysis-workbench`。
- 新增 `getStockAnalysisSummary(tsCode)` API；P0 只传 `ts_code`。
- `AnalysisWorkbenchView.vue` 展示五块内容：
  - 股票上下文
  - 中文摘要
  - 因子拆解
  - 事件证据列表
  - 风险提示

## 交互约束
- `ts_code` 缺失时显示空态且不发请求。
- `report=null` 或 `status` 为 `pending / partial` 时，显示“分析生成中 / 暂无结果”等兼容态。
- `HotNewsView.vue` 仅把 `a_share_candidates` 渲染成“进入分析”按钮，跳转到 `/analysis?ts_code=...&topic=...&source=hot_news`。
- `StockDetailView.vue` 增加“分析此股票”按钮，跳转到 `/analysis?ts_code=...&source=stock_detail`。
- 前端保留 `topic / source / event_id` 作为页面上下文展示，但 P0 不向后端透传。

## 依赖关系
- 硬依赖计划书 1 提供 `/api/analysis/stocks/{ts_code}/summary`。
- 软依赖计划书 2 补齐 `report.summary`、`risk_points` 与最终权重；未就绪时页面必须支持降级显示。

## 验收
- 无 `ts_code` 时空态正确。
- 有 `ts_code` 时能调用 `/api/analysis/stocks/{ts_code}/summary`。
- `report=null` 时能显示“分析生成中 / 暂无结果”。
- 热点页候选股和个股详情按钮都能正确跳转到 `/analysis`。
