# 下一阶段开发清单：候选股质量提升与历史报告读时补全

> 状态：计划归档，暂不执行

## Summary

- 下一阶段继续围绕“热点新闻 → 候选股 → 个股详情 → 分析工作台”主链路做产品分析深化。
- 本阶段拆成两条并行子线：
  - 候选股质量提升：增强候选股评分、可信度、新鲜度与证据可解释性。
  - 历史报告读时补全引用元数据：让旧报告在读取时也能补齐 `source / published_at / domain / metadata_status`。
- 本阶段仍不扩展到 Docker/CI、报告导出、概念成分股、离线批量回填等工程化或重型功能。

## Key Changes

### 1. 候选股质量提升

- 新增轻量候选证据缓存层 `stock_candidate_evidence_cache`，只存候选增强证据，不并入 `news_events`。
- 首批证据源固定为：
  - AkShare `stock_hot_search_baidu`
  - AkShare `stock_research_report_em`
- 在现有候选评分基础上追加：
  - 热搜命中 `+5`
  - 近 30 日研报命中 `+5`
- 扩展 `GET /api/news/impact-map` 的候选输出字段：
  - `source_breakdown`
  - `freshness_score`
  - `candidate_confidence`
  - `evidence_items`
- `evidence_items` 最多返回 `3` 条，支持 `candidate_evidence_limit` 参数，默认 `3`，最大 `5`。
- 前端热点页候选卡片新增：
  - 可信度标签
  - 新鲜度标签
  - 来源分解摘要
  - 最多 `3` 条证据短卡

### 2. 历史报告读时补全引用元数据

- 复用现有 `web_source_metadata_cache` 与 `enrich_web_sources`，不新增第二套引用服务。
- 在以下读取接口增加“读时补全”能力：
  - `GET /api/analysis/stocks/{ts_code}/summary`
  - `GET /api/analysis/stocks/{ts_code}/reports`
- 若历史报告的 `web_sources` 缺失 `source / published_at / domain / metadata_status`：
  - 优先读取 `web_source_metadata_cache`
  - 缓存未命中时做短超时最佳努力补全
  - 补全成功后回写 `analysis_reports.web_sources`
- 读时补全限流规则固定为：
  - `summary`：当前报告最多补全 `5` 条
  - `reports`：前 `3` 份报告、每份最多补全 `3` 条
  - 单次请求总抓取上限 `10` 条 URL
- 补全失败不报错，只做降级：
  - `metadata_status = unavailable`
  - `source = domain`
  - `published_at = null`

### 3. 前端引用展示

- 分析页“联网引用”卡片固定展示：
  - 标题
  - `source · published_at`
  - `domain`
  - `snippet`
  - `metadata_status`
- `published_at` 缺失时显示“时间待补全”。
- `source` 缺失时显示域名。
- 状态标签统一为：
  - `已补全`
  - `域名推断`
  - `信息缺失`
- 保持“结构化来源”和“联网引用”分区不变，不把引用内容重新混回 Markdown 正文。

## Test Plan

### Backend

- 新增候选证据缓存测试：
  - 热搜/研报缓存创建、命中缓存、过期回源、上游失败降级
- 扩展 `test_news_routes.py`：
  - `/api/news/impact-map` 返回 `source_breakdown / freshness_score / candidate_confidence / evidence_items`
  - 热搜/研报证据提升候选排序
  - `candidate_evidence_limit` 生效
- 扩展 `test_analysis_service.py` / `test_analysis_routes.py`：
  - 历史报告缺失引用元数据时，`summary` 读时补全后返回增强后的 `web_sources`
  - `reports` 列表中的旧报告可触发读时补全并回写
  - 补全失败时接口仍返回 `200`
- 扩展 `test_web_source_metadata_service.py`：
  - 缓存命中与读时回写联动正常

### Frontend

- 扩展 `HotNewsView.test.ts`：
  - 候选卡片展示来源分解、新鲜度、可信度、证据短卡
- 扩展 `AnalysisWorkbenchView.test.ts`：
  - 历史报告返回的补全后 `web_sources` 正常展示
  - 缺失 `published_at` 时显示占位
  - `metadata_status` 标签正确

### Acceptance Scenarios

- 同一主题下，带热搜/研报证据的候选股稳定排在无增强证据股票前面。
- 旧报告首次读取时，引用卡片能补全站点与时间；再次读取优先命中缓存或数据库回写结果。
- 引用补全失败不会影响分析页主内容展示。

## Assumptions

- 本阶段默认继续使用现有 AkShare 热搜/研报接口，不接入同花顺概念成分股。
- 历史报告读时补全允许对旧报告做有限同步补全并回写，这是本阶段默认策略。
- 若第三方页面限制抓取或元数据缺失，系统以“域名推断 / 信息缺失”降级，不追求更重的正文抓取。
- 本阶段结束后，再下一阶段才考虑概念成分股扩展、报告导出、Docker/CI 等能力。
