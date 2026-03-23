# P0 计划书 2：多源分析链路、权重评估与 LLM 中文解释

## 目标
- 跑通“取事件 → 语义增强 → 股价关联 → 因子归因 → 中文解释”整条分析链路。
- 把政策 / 监管事件接入统一事件消费域。
- 对 LLM 失败做好模板摘要降级，保证接口稳定返回。

## 写入范围
- `backend/app/integrations/policy_gateway.py`
- `backend/app/api/routes/news.py`
- `backend/app/services/news_repository.py`
- `backend/app/services/news_mapper_service.py`
- `backend/app/services/news_sentiment_service.py`
- `backend/app/services/key_event_extraction_service.py`
- `backend/app/services/event_link_service.py`
- `backend/app/services/factor_weight_service.py`
- `backend/app/services/analysis_prompt_service.py`
- `backend/app/services/llm_analysis_service.py`
- `backend/tests/test_news_sentiment_service.py`
- `backend/tests/test_key_event_extraction_service.py`
- `backend/tests/test_event_link_service.py`
- `backend/tests/test_factor_weight_service.py`
- `backend/tests/test_llm_analysis_service.py`

## 默认算法
- 情感阈值：`score >= 0.2` 视为正向，`score <= -0.2` 视为负向。
- 标题 / 摘要权重：`0.7 / 0.3`。
- 单条事件最多保留 `3` 个标签。
- 关联分数：`0.7 * min(abs(window_return_pct) / 10, 1.0) + 0.3 * abs(sentiment_score)`，结果截断到 `0..1`。
- 置信度：5 日窗口且标签非空为 `high`，3 日窗口为 `medium`，否则为 `low`。

## 实施要点
- 新增 `GET /api/news/policy`，把 `scope='policy'` 的事件纳入统一事件池。
- `news_sentiment_service.py` 输出 `positive | neutral | negative` 与 `-1..1` 分值。
- `key_event_extraction_service.py` 识别 `policy / regulation / announcement / earnings / industry / commodity / capital_flow / risk`。
- `event_link_service.py` 以事件发布时间后的首个交易日为锚点，向后最多取 5 个交易日窗口。
- `factor_weight_service.py` 输出 `policy / announcement / news / sentiment` 四类归一化权重。
- `analysis_prompt_service.py` 负责拼装中文 prompt。
- `llm_analysis_service.py` 复用现有 `llm_client_service.py`，并在失败时降级模板摘要。

## 边界
- 不改计划书 1 已固定的公共 schema 字段名。
- 不直接修改前端。
- 通过计划书 1 的 `analysis_service.py` 接入分析结果。

## 验收
- 有事件时能生成非空 `events[]`。
- 证据充分时能生成非空 `report.summary`。
- LLM 不可用时仍返回模板摘要。
- 规则服务、权重服务、LLM 服务均有独立单测。
