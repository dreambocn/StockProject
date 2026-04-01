# 政策数据流架构

本文档描述 `StockProject` 中“官方政策源 -> 归一化 -> 存储 -> 兼容投影 -> 前端消费”的完整链路，便于后续扩展 Provider、排查同步异常，以及对接热点/分析/个股详情页。

## 1. 总体链路

```text
官方政策源
  -> Provider 抓取列表页 / 官方 JSON / 详情页
  -> PolicyDocumentSeed
  -> normalize_policy_seed()
  -> dedupe_policy_documents()
  -> upsert_policy_documents()
  -> policy_projection_service
  -> news_events(scope='policy') 兼容投影
  -> /api/policy/* 专用查询
  -> 热点页 / 分析工作台 / 个股详情 / 政策中心
```

## 2. 当前 Provider 清单

### 2.1 已接入真实官方抓取

- `gov_cn`
  - 列表入口：`https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json`
  - 详情入口：列表内 `URL`
  - 当前补齐字段：标题、发布日期、发文机关、发文字号、成文日期、正文摘要、正文 HTML

- `pbc`
  - 列表入口：`https://www.pbc.gov.cn/tiaofasi/144941/index.html`
  - 详情入口：法规司详情页
  - 当前补齐字段：标题、发布时间、文号、附件链接、正文 HTML、正文文本

- `ndrc`
  - 列表入口：`https://www.ndrc.gov.cn/xxgk/zcfb/tz/`
  - 详情入口：通知详情页
  - 当前补齐字段：标题、发布时间、文号、附件链接、正文摘要

- `miit`
  - 列表入口：工业和信息化部官方 `build/unit` 列表接口
  - 详情入口：文件发布详情页
  - 当前补齐字段：标题、发布时间、摘要、附件链接

- `csrc`
  - 列表入口：`https://www.csrc.gov.cn/csrc/c100028/common_list.shtml`
  - 详情入口：证监会要闻详情页
  - 当前补齐字段：标题、发布时间、发布机构、摘要

- `npc`
  - 列表入口：`http://www.npc.gov.cn/npc/c2/c12435/c12488/`
  - 详情入口：中国人大网法律文件详情页
  - 当前补齐字段：标题、发布时间、来源、正文文本

### 2.2 当前仍需继续增强的点

- 更深层正文抽取与正文 HTML 清洗
- 附件名称与附件类型增强
- 个别站点分页/历史回看能力
- 更稳的正文容器解析，减少站点模板调整后的脆弱性

## 3. 统一数据结构

所有 Provider 最终都输出 `PolicyDocumentSeed`，核心字段如下：

- `source`
- `source_document_id`
- `title`
- `summary`
- `document_no`
- `issuing_authority`
- `policy_level`
- `category`
- `published_at`
- `effective_at`
- `url`
- `attachment_urls`
- `content_text`
- `content_html`
- `raw_payload`

归一化后会进一步补齐：

- `macro_topic`
- `industry_tags`
- `market_tags`
- `url_hash`
- `metadata_status`
- `projection_status`

## 4. 兼容旧链路方式

`policy_documents` 是政策主数据表，`news_events(scope='policy')` 只是兼容投影。

这意味着：

- 政策检索、详情、附件应优先读取 `policy_documents`
- 热点、分析、影响图等旧链路仍可继续读取 `news_events`
- Provider 不允许直接写 `news_events`
- 兼容投影必须统一经 `policy_projection_service`

## 5. 可观测性

### 5.1 同步任务指标

`policy_sync_service` 会把以下指标写入 `system_job_runs.metrics_json`：

- `provider_count`
- `raw_count`
- `normalized_count`
- `inserted_count`
- `updated_count`
- `deduped_count`
- `failed_provider_count`
- `successful_provider_count`
- `successful_providers`
- `failed_providers`
- `provider_stats`

其中 `provider_stats` 用于记录每个 Provider 的源级指标：

- `provider`
- `status`
- `error_type`
- `raw_count`
- `normalized_count`

### 5.2 健康检查

`GET /api/health/readiness` 现在除了 `postgres / redis / smtp` 外，还会返回 `policy_sync` 摘要：

- 当前是否启用政策同步
- 配置中的 Provider 数量
- 每个 Provider 的最大抓取条数
- 最近一次 `policy_sync` 的状态
- 最近一次同步的成功源 / 失败源摘要

## 6. 手动同步命令

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run python scripts\sync_policy_documents.py
```

如果只想触发 API 入口，可使用管理员账号调用：

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/policy/sync' -Headers @{
  Authorization = 'Bearer <ADMIN_TOKEN>'
}
```

## 7. 排障要点

### 7.1 官方站点能抓到，但数据库没有数据

优先检查：

- `POSTGRES_JDBC_URL` 是否指向可访问的实例
- `127.0.0.1:5432` 是否真的有 PostgreSQL 在监听
- `uv run python scripts\sync_policy_documents.py` 是否报数据库连接错误

### 7.2 同步任务成功率低

优先检查：

- `provider_stats` 中哪些 Provider `status=failed`
- `error_type` 是否集中在超时、连接拒绝或 HTML 结构变更
- `POLICY_SOURCE_MAX_ITEMS_PER_PROVIDER` 是否设置过大

### 7.3 页面已接线但看不到政策

优先检查：

- `/api/policy/documents` 是否已有真实数据
- 最近一次 `policy_sync` 是否失败
- 热点主题 / 个股关键词是否能命中当前政策的 `macro_topic` 或标题关键词
