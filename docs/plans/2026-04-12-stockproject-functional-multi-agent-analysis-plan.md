# StockProject Functional Multi-Agent Stock Analysis Plan

**Goal:** 为 `StockProject` 的股票分析模块建立一套“纯职能型多 Agent 协同研判”架构，将当前单次 LLM 报告生成升级为“研究规划 -> 证据检索 -> 证据审计 -> 假设构建 -> 反向质询 -> 最终裁决”的流水线式分析系统，同时保持与现有分析工作台、Analysis Worker、历史报告和导出能力兼容。

**Architecture:** 方案以现有 `analysis_generation_sessions + analysis_reports + Analysis Worker + SSE` 为主骨架，不推翻现有链路，而是在 `analysis_service.py` 的“选择事件并直接调用单次 LLM”位置前后插入一个新的纯职能编排层。该编排层优先复用仓库现有结构化数据与抓取能力，由确定性服务完成取证与审计，再由多个职责单一的 Agent 逐步完成假设提出、漏洞挑战与最终裁决。

**Tech Stack:** FastAPI、SQLAlchemy Async、Alembic、Redis、OpenAI Responses API、Vue 3、TypeScript、Pytest、Vitest

---

## 0. 背景与问题定义

### 0.1 当前仓库已有的分析能力

当前 `StockProject` 的分析模块已经具备较好的产品与工程基础：

- 后端入口位于 `backend/app/api/routes/analysis.py`
- 运行主流程位于 `backend/app/services/analysis_service.py`
- Prompt 构造位于 `backend/app/services/analysis_prompt_service.py`
- LLM 调用位于 `backend/app/services/llm_analysis_service.py` 与 `backend/app/services/llm_client_service.py`
- 分析执行不是同步接口，而是：
  - 创建分析会话
  - Analysis Worker 后台处理
  - SSE 增量推送摘要
  - 报告归档与历史查看
- 前端 `frontend/src/views/AnalysisWorkbenchView.vue` 已具备：
  - 摘要展示
  - 流式生成
  - 历史报告切换
  - 证据与来源展示
  - 导出
  - 与热点页、个股详情、自选股联动

### 0.2 当前实现的核心限制

尽管现有分析链路已经不是“把模型输出直接贴回页面”，但当前本质上仍是单 Agent 模式：

- 单一 system instruction
- 单一 user prompt
- 单次模型调用
- 单份最终 Markdown 报告
- 可选 `use_web_search` 仅为整场会话的统一开关

这会带来几个长期问题：

1. **分析结论过于集中**
   - 最终结论只有一个生成来源，缺少显式的反方挑战和假设竞争机制
2. **问题定位困难**
   - 当结果质量不佳时，很难判断究竟是检索不充分、证据质量差、推理链条跳跃，还是提示词引导方向失衡
3. **渠道扩展困难**
   - 新增来源时只能继续堆进单一 Prompt，后续 Prompt 会越来越长、越来越难调
4. **可解释性有限**
   - 前端虽然能展示证据和引用，但仍无法清晰解释“系统是如何从多类证据收敛到最终结论的”

### 0.3 为什么选择“纯职能型多 Agent”

多 Agent 有两种常见拆法：

- 按立场拆：多头 / 空头 / 政策 / 裁判
- 按职能拆：规划 / 检索 / 审计 / 假设 / 质询 / 裁决

本计划选择 **纯职能型多 Agent**，原因如下：

1. 更贴合当前仓库的数据基础设施
   - 仓库已有结构化事件、政策投影、来源补全、因子权重、候选证据等能力，更适合作为“研究流水线”的组成层，而不是简单再包几层不同口吻的 Prompt
2. 更易做质量治理
   - 每个阶段都有明确输入输出，更容易做日志、指标、回放和评测
3. 更适合后续扩展新来源
   - 新增来源优先影响检索和审计层，不需要同时改所有判断型 Agent
4. 更容易定位问题
   - 可以明确区分“没找到证据”“证据审计不充分”“候选假设不完整”“挑战力度不足”“最终裁决偏差”

### 0.4 本计划解决的问题

本计划要解决的是：

1. 将单一分析生成改造成多阶段研究流水线
2. 让不同职责的 Agent 只承担单一任务，减少 Prompt 混杂
3. 保持与当前工作台、历史报告、导出能力兼容
4. 在前端同时提供：
   - 普通用户友好的“最终结论视图”
   - 专业用户可见的“研究流水线视图”
5. 为后续新增数据源、评测体系、提示词版本治理和成本治理预留结构

### 0.5 本计划暂不做的内容

为了保证第一阶段收敛，本轮明确不做：

- 接入新的外部资讯 Provider
- 开放式可配置 Agent 市场
- 多轮 Agent 辩论或无上限回合制交互
- 训练或微调专用股票模型
- 全量回放历史报告并补齐多 Agent 中间结果
- 将 `watchlist_daily` 立即切换到多 Agent 默认路径

---

## 1. 总体方案概览

### 1.1 目标架构

```text
用户触发分析
  -> 创建 analysis_generation_session
  -> Analysis Worker 领取会话
  -> 纯职能型多 Agent 编排层启动
     -> Research Planner Agent 生成研究计划
     -> Evidence Retrieval Executor 按计划拉取证据
     -> Evidence Audit Agent 审计证据质量与冲突
     -> Hypothesis Builder Agent 构建候选假设
     -> Challenge Agent 对候选假设逐条发起挑战
     -> Decision Agent 结合挑战结果输出最终结论
  -> 落 analysis_agent_runs 中间产物
  -> 落 analysis_reports 最终报告
  -> SSE 推送阶段进度与最终结论
  -> 前端默认展示最终结论，可切换查看研究流水线
```

### 1.2 核心设计原则

1. **确定性取证优先，LLM 判断后置**
   - 取证、去重、来源补全、时间窗约束尽量由后端确定性逻辑完成
2. **每个 Agent 只做一类事**
   - 避免让单个 Agent 既负责检索又负责结论又负责审计
3. **最终报告保持兼容**
   - `analysis_reports.summary` 继续保存最终面向用户的 Markdown 内容
4. **中间产物必须可落库、可回看、可测试**
   - 不是只在内存里跑完然后丢掉
5. **失败可降级**
   - 任一中间阶段失败，不应导致工作台直接空白

### 1.3 第一阶段运行模式

第一阶段定义固定模式：

- 手动工作台分析默认支持 `functional_multi_agent`
- `watchlist_daily` 保持现有 `single` 模式
- 使用固定 6 个职责角色
- 不开放用户自定义 Agent 数量和角色
- 不做跨股票联合分析

---

## 2. 六类 Agent 的职责划分

### 2.1 Research Planner Agent

#### 作用

负责把“这次分析应该看什么”先规划清楚，而不是直接开始写结论。

#### 输入

- `ts_code`
- 股票名称、最新快照
- 主题上下文 `topic`
- 锚点事件 `anchor_event_id`
- 是否允许 `use_web_search`
- 当前可用渠道清单
- 默认研究预算参数

#### 输出

结构化 `research_plan`，至少包含：

- 本次重点研究方向
- 需要优先拉取的证据桶
- 每类证据数量上限
- 是否建议启用 web search
- 哪些证据缺口需要重点补
- 对应的执行顺序

#### 为什么单独拆出这个角色

当前系统默认由工程逻辑决定“拉哪些事件 + 取多少条 + 是否走 web search”，随着来源增加，这个决策会越来越复杂。单独引入 Planner 可以把“研究策略”显式化、可持久化、可回看。

### 2.2 Evidence Retrieval Agent

#### 作用

负责执行研究计划，把原始证据拉齐。

#### 设计说明

这个角色采用“LLM 计划 + 确定性执行器”的混合模式：

- 是否检索、检索哪些桶、每类多少条由 Planner 决定
- 真正执行取证仍由后端服务完成，不把外部抓取权交给模型自由发挥

#### 第一阶段可复用渠道

- `news_events`
- `policy_documents`
- `policy` 投影事件
- `akshare` 新闻与公告
- `tushare` 宏观/政策/日线等数据
- 候选证据：
  - 百度热搜
  - 东方财富研报
- 可选 `web_search`

#### 输出

`evidence_ledger_raw`，每条证据至少带：

- 证据类型
- 标题
- 摘要
- 时间
- 渠道
- 来源 URL
- 与当前股票的关联维度
- 是否来自结构化渠道或联网搜索

### 2.3 Evidence Audit Agent

#### 作用

对原始证据账本做质量审核和冲突整理。

#### 关注点

- 是否重复
- 是否过期
- 来源是否可信
- 是否只靠单一来源
- 是否存在时间错配
- 是否存在正反冲突证据
- 是否缺少关键验证项

#### 输出

两个结构化产物：

1. `evidence_ledger_audited`
   - 审计后的可用证据清单
2. `evidence_scorecard`
   - 各类证据的评分与告警

#### 为什么这个角色很关键

如果没有审计层，后面的假设构建和最终裁决都只是基于“未经清洗的原始噪音”做推理，系统看起来很智能，但很难稳定。

### 2.4 Hypothesis Builder Agent

#### 作用

基于审计后的证据账本提出候选假设，而不是直接给单一结论。

#### 第一阶段固定输出

统一输出 3 个候选假设：

- `bullish_hypothesis`
- `neutral_hypothesis`
- `bearish_hypothesis`

#### 每个候选假设必须包含

- 一句话判断
- 主要支持证据
- 主要反向证据
- 成立条件
- 失效条件
- 初始置信度

#### 设计原因

候选假设机制比“直接给结论”更适合后续被 Challenge Agent 挑战，也更适合前端以卡片形式展示“系统曾考虑过哪些可能性”。

### 2.5 Challenge Agent

#### 作用

专门质疑和攻击候选假设，职责是找漏洞，不负责给出最终答案。

#### 主要检查内容

- 结论是否依赖单一来源
- 是否把公告、政策、新闻混成了同等强度的证据
- 是否忽略了价格与成交量验证
- 是否存在因果倒置
- 是否存在时间错配
- 是否把主题逻辑直接等价成个股业绩逻辑
- 是否遗漏明显反证

#### 输出

`challenge_report`，按候选假设逐条给出：

- 主要漏洞
- 反证力度
- 剩余可信度削弱比例
- 未解决的疑点

### 2.6 Decision Agent

#### 作用

消费全部前置阶段产物，输出最终面向用户的报告。

#### 必须说明的内容

- 最终采纳的是哪个候选假设
- 为什么采纳
- 为什么没有采纳其余假设
- 当前最强证据是什么
- 当前最强不确定性是什么

#### 输出

- 用户可见 Markdown 报告
- 最终裁决元数据：
  - `selected_hypothesis`
  - `decision_confidence`
  - `decision_reason_summary`

---

## 3. 数据与证据渠道设计

### 3.1 现有渠道的角色定位

第一阶段不引入新 Provider，渠道按职责分层使用：

#### A. 结构化主数据渠道

- `news_events`
- `analysis_event_links`
- `stock_daily_snapshots`
- `policy_documents`

定位：

- 作为研究底盘
- 优先级最高
- 优先用于 Audit 与 Hypothesis 阶段

#### B. 实时补充渠道

- `akshare` 个股新闻
- `akshare` 公告
- `tushare` 行情与宏观/政策信号

定位：

- 用于填补结构化缓存时间差
- 提供增量证据

#### C. 候选增强渠道

- 百度热搜
- 东方财富研报

定位：

- 不直接决定结论
- 用于补强“市场关注度”“研究关注度”

#### D. 联网搜索渠道

- `web_search`

定位：

- 仅在 Planner 判定确有必要且系统配置允许时使用
- 第一阶段不是默认主渠道

### 3.2 证据账本统一格式

为了让多个角色共享上下文，所有证据必须落成统一账本格式。建议统一字段如下：

- `evidence_id`
- `bucket`
- `scope`
- `title`
- `summary`
- `published_at`
- `source`
- `provider`
- `url`
- `ts_code`
- `topic`
- `event_type`
- `source_priority`
- `is_structured`
- `is_web_search`
- `audit_flags`
- `score`

### 3.3 证据分桶

Planner 输出研究计划时，以固定证据桶组织：

- `price_and_volume`
- `stock_news`
- `announcements`
- `policy_documents`
- `policy_projected_events`
- `candidate_evidence`
- `web_search`

这样后续加渠道时，只需映射到已有 bucket，不需要重做前后端整体协议。

---

## 4. 编排层与运行时设计

### 4.1 新的运行主流程

基于现有 `run_analysis_session_by_id()` 主流程，改造成以下阶段：

1. `prepare_context`
   - 读取股票基础信息
   - 选择基础事件
   - 准备价格与主题上下文
2. `planning`
   - 调用 Planner Agent 生成研究计划
3. `retrieving_evidence`
   - 按研究计划拉取证据
4. `auditing_evidence`
   - 执行来源补全、冲突审计、评分
5. `building_hypotheses`
   - 构建候选假设
6. `challenging_hypotheses`
   - 对假设发起反向挑战
7. `decisioning`
   - 生成最终报告
8. `finalizing`
   - 落库、缓存、推送完成事件

### 4.2 并发策略

第一阶段不做过度并发，采用保守顺序：

- Planner 单独执行
- Retrieval 由确定性服务串行或有限并发执行
- Audit 单独执行
- Hypothesis 单独执行
- Challenge 单独执行
- Decision 单独执行

原因：

- 纯职能型流水线更强调阶段依赖，而不是立场并行
- 第一阶段重点是稳定性和可观测性，而不是极限速度

### 4.3 会话缓存与幂等

保留现有：

- `analysis_key`
- 活跃会话缓存
- 新鲜报告缓存

新增约束：

- `analysis_mode` 必须进入 `analysis_key`
- 避免单 Agent 与多 Agent 会话互相复用缓存

### 4.4 降级策略

#### 单阶段失败

- `planning` 失败：回退到默认研究计划模板
- `retrieving_evidence` 部分失败：标记缺口，继续
- `auditing_evidence` 失败：保留原始证据账本，降低最终置信度
- `hypothesis` 失败：使用规则化三假设模板
- `challenge` 失败：明确标记“反证覆盖不足”
- `decision` 失败：回退到规则化最终摘要

#### 全流程失败

- 沿用现有规则化摘要逻辑，工作台仍返回 `partial`

---

## 5. 数据库与持久化设计

### 5.1 保持兼容的主表

#### `analysis_generation_sessions`

继续作为分析会话主表，不替换。

建议新增字段：

- `analysis_mode`
- `orchestrator_version`
- `role_count`
- `role_completed_count`
- `active_role_key`

#### `analysis_reports`

继续作为最终报告主表，不替换。

建议新增字段：

- `analysis_mode`
- `orchestrator_version`
- `selected_hypothesis`
- `decision_confidence`
- `decision_reason_summary`

### 5.2 新增中间结果表 `analysis_agent_runs`

该表是第一阶段最关键的新表，用于保存每个职责角色的产物。

建议字段：

- `id`
- `session_id`
- `report_id`
- `role_key`
- `role_label`
- `status`
- `sort_order`
- `summary`
- `input_snapshot`
- `output_payload`
- `used_web_search`
- `web_search_status`
- `web_sources`
- `prompt_version`
- `model_name`
- `reasoning_effort`
- `token_usage_input`
- `token_usage_output`
- `cost_estimate`
- `failure_type`
- `started_at`
- `completed_at`
- `created_at`
- `updated_at`

### 5.3 为什么 V1 不单独建更多表

例如：

- `analysis_research_plans`
- `analysis_evidence_ledgers`
- `analysis_hypothesis_sets`

这些拆法从领域建模角度更细，但第一阶段会显著增加迁移、Repository 和前端读取复杂度。V1 更合适的做法是：

- 统一先落 `analysis_agent_runs.output_payload`
- 等确认字段长期稳定后，再把某些中间产物拆成独立表

---

## 6. API 设计

### 6.1 创建会话接口

`POST /api/analysis/stocks/{ts_code}/sessions`

新增请求字段：

- `analysis_mode?: 'single' | 'functional_multi_agent'`

行为规则：

- 手动分析允许切到 `functional_multi_agent`
- `watchlist_daily` 第一阶段仍强制走 `single`

### 6.2 会话状态接口

`GET /api/analysis/sessions/{session_id}`

新增字段：

- `analysis_mode`
- `pipeline_stage`
- `active_role_key`
- `role_progress`

### 6.3 摘要与归档接口

`GET /api/analysis/stocks/{ts_code}/summary`

`GET /api/analysis/stocks/{ts_code}/reports`

在 `AnalysisReportResponse` 中新增：

- `analysis_mode`
- `orchestrator_version`
- `selected_hypothesis`
- `decision_confidence`
- `decision_reason_summary`
- `pipeline_roles`

其中 `pipeline_roles` 为角色列表，每项包含：

- `role_key`
- `role_label`
- `status`
- `summary`
- `output_payload`
- `used_web_search`
- `web_search_status`
- `web_sources`
- `prompt_version`
- `model_name`
- `reasoning_effort`
- `failure_type`

### 6.4 SSE 事件扩展

保留现有：

- `status`
- `delta`
- `completed`
- `error`

新增：

- `role_status`
- `role_delta`
- `role_completed`
- `pipeline_checkpoint`

兼容规则：

- 现有前端忽略新事件仍可运行
- `delta` 继续只代表最终用户可见摘要，不混入中间角色自由文本

---

## 7. 前端展示设计

### 7.1 双层模式

第一阶段前端采用双层模式：

#### 默认层：最终结论视图

面向普通用户，保持工作台易读：

- 最终结论
- 最终置信度
- 采纳的候选假设
- 关键证据
- 风险提示
- 来源与运行元信息

#### 专业层：研究流水线视图

面向希望理解推理过程的用户：

- Research Planner 输出的研究计划
- Evidence Retrieval 的证据分桶概览
- Evidence Audit 的评分卡与冲突提示
- Hypothesis Builder 的三种候选假设
- Challenge 的反驳结果
- Decision 的最终采纳理由

### 7.2 页面结构建议

在 `AnalysisWorkbenchView.vue` 中新增：

1. 协同模式标识
2. 视图切换：
   - `最终结论`
   - `研究流水线`
3. 流水线时间轴
4. 角色卡片区

### 7.3 历史报告兼容

- 老报告：
  - 没有 `pipeline_roles`
  - 继续按当前单报告视图展示
- 新报告：
  - 额外展示“纯职能协同”标签
  - 支持切换查看中间角色结果

---

## 8. Prompt 与角色输出规范

### 8.1 总原则

- 所有角色都必须输出结构化 JSON 或可解析 Markdown
- 第一阶段优先使用 JSON 结构体落库，再由前端决定如何渲染
- 只有 `Decision Agent` 需要输出最终用户可见 Markdown

### 8.2 各角色输出约束

#### Planner

- 严格输出研究计划 JSON
- 不允许输出投资结论

#### Retrieval

- 不输出结论文本
- 只输出取证结果与命中说明

#### Audit

- 不输出投资建议
- 只输出证据质量审计结果

#### Hypothesis

- 固定三假设格式
- 每条假设都必须附支持证据和反向证据

#### Challenge

- 只负责挑错
- 不负责给出最终建议

#### Decision

- 输出最终 Markdown
- 必须显式说明“采纳理由”和“未采纳理由”

---

## 9. 运行指标与可观测性

### 9.1 每个角色必须记录

- 开始时间
- 完成时间
- 耗时
- 模型名称
- 推理档位
- token 输入输出
- 成本估算
- 是否使用 web search
- 失败类型

### 9.2 整场分析必须记录

- 总时长
- 成功角色数
- 失败角色数
- 使用的证据桶数量
- 使用 web search 的角色数量
- 最终采纳的候选假设

### 9.3 后台任务中心扩展

`analysis_generate` 的 `metrics_json` 增加：

- `analysis_mode`
- `role_count`
- `role_success_count`
- `selected_hypothesis`
- `decision_confidence`

---

## 10. 测试计划

### 10.1 后端单元测试

#### Planner

- 能输出结构化研究计划
- 不会输出最终投资建议

#### Retrieval

- 能按研究计划限制证据数量
- 不会在禁用 web search 时错误触发外部检索

#### Audit

- 能识别重复证据
- 能识别过期证据
- 能识别来源单一问题
- 能识别相互冲突证据

#### Hypothesis

- 始终输出三条候选假设
- 候选假设结构稳定

#### Challenge

- 每条候选假设都能得到挑战结果
- 空假设或弱假设场景不报错

#### Decision

- 能根据 Challenge 结果稳定选出最终结论
- 能说明未采纳原因

### 10.2 后端集成测试

- 创建 `functional_multi_agent` 会话后，能顺序落多条 `analysis_agent_runs`
- `summary` 与 `reports` 接口返回新字段
- SSE 能输出角色阶段事件
- 单个角色失败时最终报告仍能生成
- `watchlist_daily` 默认路径不受影响

### 10.3 前端测试

- 默认显示最终结论层
- 可以切换到研究流水线层
- 新旧报告可共存
- 单角色失败场景下 UI 能正确提示

### 10.4 验收标准

1. 用户在工作台可以看到最终结论，不会因为多 Agent 而变复杂难懂
2. 专业用户可以展开研究流水线，看到系统如何从证据走到结论
3. 任一中间角色失败时，页面仍然可用
4. 历史单 Agent 报告仍能正常打开

---

## 11. 分阶段实施建议

### Phase 1：基础设施层

- 增加 `analysis_mode`
- 增加 `analysis_agent_runs`
- 扩展 schema 与 API 返回结构

### Phase 2：后端编排层

- 新建纯职能型编排服务
- 接入 Planner / Retrieval / Audit / Hypothesis / Challenge / Decision 六阶段

### Phase 3：前端双层视图

- 默认结论层
- 流水线视图
- 角色状态与阶段时间轴

### Phase 4：指标与导出

- 补齐角色维度指标
- 导出时带上流水线摘要

### Phase 5：灰度与扩展

- 手动分析稳定后，再评估是否扩到 `watchlist_daily`
- 稳定后再考虑新增外部 Provider

---

## 12. 推荐落地文件范围

第一阶段预计会涉及以下关键文件或模块：

### 后端

- `backend/app/services/analysis_service.py`
- `backend/app/services/llm_analysis_service.py`
- `backend/app/services/analysis_repository.py`
- `backend/app/schemas/analysis.py`
- `backend/app/models/analysis_generation_session.py`
- `backend/app/models/analysis_report.py`
- `backend/app/api/routes/analysis.py`

建议新增：

- `backend/app/models/analysis_agent_run.py`
- `backend/app/services/analysis_orchestrator_service.py`
- `backend/app/services/analysis_role_registry.py`
- `backend/app/services/analysis_research_plan_service.py`
- `backend/app/services/analysis_evidence_audit_service.py`
- `backend/app/services/analysis_hypothesis_service.py`
- `backend/app/services/analysis_challenge_service.py`
- `backend/app/services/analysis_decision_service.py`

### 前端

- `frontend/src/api/analysis.ts`
- `frontend/src/views/AnalysisWorkbenchView.vue`
- `frontend/src/views/AnalysisWorkbenchView.test.ts`

建议新增：

- `frontend/src/components/analysis/AnalysisPipelinePanel.vue`
- `frontend/src/components/analysis/AnalysisRoleCard.vue`
- `frontend/src/components/analysis/AnalysisHypothesisCompare.vue`

### 测试

- `backend/tests/test_analysis_service.py`
- `backend/tests/test_analysis_routes.py`
- `backend/tests/test_analysis_job_integration.py`
- `frontend/src/views/AnalysisWorkbenchView.test.ts`

---

## 13. 结论

这套纯职能型多 Agent 方案的核心不是“让多个模型一起写报告”，而是把现有分析模块升级成一个结构化研究流水线：

- 先规划研究任务
- 再统一取证
- 再审计证据质量
- 再构建候选假设
- 再专门挑战这些假设
- 最后才输出用户可见结论

对 `StockProject` 而言，这条路径比“多头/空头各写一篇”更适合作为长期主线，因为它更贴合当前仓库已经具备的结构化数据基础，也更容易做质量、成本和运行稳定性的持续治理。
