# StockProject Policy Data Full-Chain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `StockProject` 建立一套“国家政策数据获取 -> 归一化 -> 存储 -> 查询 -> 投影到现有新闻/分析链路 -> 前端消费”的完整闭环，使项目不再只依赖财经新闻和日历侧信号，而能直接消费官方政策原文与监管文件。

**Architecture:** 在现有 `news_events + analysis + impact-map + system_job_runs` 框架上新增独立 `policy_document` 领域，采用“多官方来源 Provider -> 统一归一化 DTO -> 权威表持久化 -> 向 `news_events` 兼容投影 -> 专用 Policy API + 现有分析/热点链路复用”的渐进式方案。该方案优先保证与现有 `GET /api/news/policy`、`/api/news/events`、分析工作台兼容，不做一次性大改。

**Tech Stack:** FastAPI、SQLAlchemy Async、Alembic、Redis、httpx、Vue 3、TypeScript、Pytest、Vitest

---

## 0. 当前现状与目标边界

### 0.1 当前现状

当前仓库已有政策相关入口，但本质仍是“政策相关新闻流”，不是“官方政策文档库”：

- `backend/app/integrations/policy_gateway.py`
  - 当前仅用 `TushareGateway.fetch_cctv_news()` 与 `fetch_economic_calendar()` 拼装政策事件
- `backend/app/api/routes/news.py`
  - 已提供 `GET /api/news/policy`
  - 已把政策相关数据持久化为 `news_events(scope='policy')`
- `frontend/src/views/HotNewsView.vue`
  - 已有主题筛选和影响图谱，但没有“政策原文中心 / 政策详情页 / 政策检索”

### 0.2 本计划解决的问题

本计划目标不是简单“再加一个新闻源”，而是建立完整政策数据链路：

1. 采集官方政策原文与官方发布/解读
2. 统一归一化政策结构
3. 持久化政策主数据与附件元数据
4. 为现有 `news_events` / `impact-map` / `analysis` 提供兼容投影
5. 增加独立的政策检索与详情 API
6. 增加前端政策浏览与联动入口
7. 把同步过程纳入 `system_job_runs` 与后台任务中心

### 0.3 本计划不做的内容

为了避免范围失控，本轮不做：

- 政策 PDF/OCR 深度抽取
- 政策全文 NLP 摘要模型训练
- 全量历史法规回填到多年级别
- 通用网页爬虫框架平台化
- 复杂权限管理与全文检索引擎（如 ES / OpenSearch）

---

## 1. 目标全链路架构

```text
官方政策源
  -> Provider 抓取
  -> 统一 DTO 归一化
  -> 去重与版本判定
  -> policy_documents / policy_document_attachments 持久化
  -> system_job_runs 记录同步结果
  -> 兼容投影到 news_events(scope='policy')
  -> /api/policy/* 专用查询
  -> /api/news/policy / /api/news/events 兼容读取
  -> impact-map / analysis 复用政策事件
  -> 前端政策中心 / 热点页 / 分析工作台使用
```

### 1.1 权威数据与兼容数据双轨

- **权威主表**
  - `policy_documents`
  - `policy_document_attachments`
- **兼容投影表**
  - `news_events(scope='policy')`

设计原则：

- 政策原文必须落到独立领域模型，不能继续只作为 `news_events` 的一种“新闻类型”
- 现有前端和分析链路已经大量依赖 `news_events`，因此必须保留兼容投影，避免大面积断链

### 1.2 同步与使用职责划分

- **Provider 层**
  - 只负责从官方站点拉取原始数据并转换为 Provider DTO
- **Normalization 层**
  - 负责统一字段、主题标签、发文机关、文号、时间、链接、正文摘要
- **Repository 层**
  - 负责 upsert、去重、查询、版本管理
- **Projection 层**
  - 负责将 `policy_documents` 生成给现有热点/分析链路可消费的 `news_events`
- **API 层**
  - 提供专用政策检索 / 详情 / 后台同步入口
- **Frontend 层**
  - 提供政策中心、详情跳转、热点/分析联动

---

## 2. 官方数据源矩阵

### 2.1 第一阶段必须接入

#### 1) 国务院政策文件库

- 价值：
  - 最高优先级的国家级政策文件源
  - 适合宏观政策、产业政策、跨部委综合政策
- 目标用途：
  - 作为“政策原文主数据”的第一权威来源

#### 2) 国家法律法规数据库

- 价值：
  - 法律、行政法规、部分规范性文件的权威查询入口
  - 适合补齐法规层级和长期有效文件
- 目标用途：
  - 作为高层级法规数据的补充底座

#### 3) 中国人民银行政策/新闻栏目

- 价值：
  - 货币政策、金融稳定、支付清算、宏观审慎直接影响市场
- 目标用途：
  - 为 `monetary_policy` 与金融主题映射提供高质量数据

#### 4) 中国证监会政府信息公开

- 价值：
  - 资本市场监管、上市公司规则、发行并购、基金/券商监管的重要来源
- 目标用途：
  - 为资本市场政策链路提供直接监管文件

#### 5) 国家发展改革委政策发布

- 价值：
  - 产业政策、能源、价格、投资、宏观调控的重要来源
- 目标用途：
  - 作为产业与宏观政策的重要补充

#### 6) 工业和信息化部政策文件

- 价值：
  - 制造业、电子信息、新能源汽车、半导体、数字经济政策的重要来源
- 目标用途：
  - 强化行业政策到题材/板块/个股的映射

### 2.2 第二阶段扩展

- 财政部
- 国家金融监督管理总局
- 市场监管总局
- 商务部
- 住建部
- 国新办发布会 / 政策吹风会文字实录

### 2.3 Provider 输出统一字段

所有 Provider 必须输出统一的 `PolicyDocumentSeed`：

```python
@dataclass(slots=True)
class PolicyDocumentSeed:
    # 统一政策种子结构，便于后续做多源去重与统一入库。
    source: str
    source_document_id: str | None
    title: str
    summary: str | None
    document_no: str | None
    issuing_authority: str | None
    policy_level: str | None
    category: str | None
    published_at: datetime | None
    effective_at: datetime | None
    url: str
    attachment_urls: list[str]
    content_text: str | None
    content_html: str | None
    raw_payload: dict[str, object]
```

---

## 3. 数据模型设计

### 3.1 主表 `policy_documents`

建议新增模型文件：

- `backend/app/models/policy_document.py`

建议字段：

- `id: str`
- `source: str`
- `source_document_id: str | None`
- `url_hash: str`
- `title: str`
- `summary: str | None`
- `document_no: str | None`
- `issuing_authority: str | None`
- `policy_level: str | None`
- `category: str | None`
- `macro_topic: str | None`
- `industry_tags_json: JSON`
- `market_tags_json: JSON`
- `published_at: datetime | None`
- `effective_at: datetime | None`
- `expired_at: datetime | None`
- `url: str`
- `content_text: Text | None`
- `content_html: Text | None`
- `raw_payload_json: JSON | None`
- `metadata_status: str`
- `projection_status: str`
- `sync_job_id: str | None`
- `created_at`
- `updated_at`

建议唯一约束：

- `uq_policy_documents_source_source_document_id`
- `uq_policy_documents_source_url_hash`

### 3.2 附件表 `policy_document_attachments`

建议新增模型文件：

- `backend/app/models/policy_document_attachment.py`

建议字段：

- `id`
- `document_id`
- `attachment_url`
- `attachment_name`
- `attachment_type`
- `attachment_hash`
- `created_at`
- `updated_at`

### 3.3 不新增独立批次表，复用统一任务平台

本轮不新增 `policy_sync_batches`，理由：

- 仓库当前已经有 `system_job_runs`
- 政策同步可直接用 `job_type='policy_sync'`
- 每次同步的 provider 统计、失败原因、抓取量写入 `metrics_json / payload_json`

这样能减少表数量、降低迁移复杂度，并让后台任务中心直接看到政策同步任务。

---

## 4. 接口设计

### 4.1 后端新增专用政策 API

建议新增：

- `GET /api/policy/documents`
  - 支持 `authority`、`category`、`macro_topic`、`published_from`、`published_to`、`keyword`
- `GET /api/policy/documents/{document_id}`
  - 返回正文、附件、标签、关联主题
- `GET /api/policy/filters`
  - 返回 authority/category/topic 聚合值
- `POST /api/admin/policy/sync`
  - 管理员手动触发同步
- `GET /api/admin/policy/sources`
  - 返回各 provider 开关与最近同步摘要

建议新增文件：

- `backend/app/api/routes/policy.py`
- `backend/app/schemas/policy.py`

### 4.2 保持现有兼容接口

现有接口继续保留：

- `GET /api/news/policy`
- `GET /api/news/events?scope=policy`

但其数据来源改为：

- 先读 `policy_documents`
- 再投影生成或同步 `news_events(scope='policy')`

### 4.3 分析和热点链路使用方式

- `impact-map` 继续使用 `news_events`
- `analysis_service` 继续从 `news_events` 拉政策事件候选
- 但政策事件的 `source/provider/title/summary/url/macro_topic` 来自 `policy_documents` 投影

这样可以保证现有分析逻辑不需要先大改。

---

## 5. 前端使用链路设计

### 5.1 新增“政策中心”页面

建议新增：

- `frontend/src/views/PolicyDocumentsView.vue`
- `frontend/src/views/PolicyDocumentsView.test.ts`
- `frontend/src/api/policy.ts`

页面能力：

- 按发文机关筛选
- 按政策类别筛选
- 按宏观主题筛选
- 按关键词搜索
- 列表 + 详情抽屉
- 原文链接、附件链接

### 5.2 热点页与个股页联动

建议增强：

- `HotNewsView.vue`
  - 当主题下命中政策文档时，显示“相关政策”卡片
- `StockDetailView.vue`
  - 增加“相关政策”区块

### 5.3 分析工作台联动

建议增强：

- `AnalysisWorkbenchView.vue`
  - 在结构化引用区单独标出政策类引用
  - 区分“政策原文 / 政策解读 / 新闻事件”

---

## 6. 详细任务拆解

### Task 1: 建立政策文档领域模型与 Alembic 迁移

**Files:**
- Create: `backend/app/models/policy_document.py`
- Create: `backend/app/models/policy_document_attachment.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260331_0005_policy_documents.py`
- Test: `backend/tests/test_policy_models.py`

**Step 1: Write the failing test**

```python
def test_policy_document_unique_by_source_and_url_hash():
    # 同一来源同一 URL 只能保留一份政策文档，避免重复抓取污染主表。
    ...
```

**Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_models.py::test_policy_document_unique_by_source_and_url_hash
```

Expected: FAIL with missing model / missing table

**Step 3: Write minimal implementation**

```python
class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    # 关键字段：唯一键优先选择 source + source_document_id / url_hash 双保险。
    ...
```

**Step 4: Run test to verify it passes**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_models.py::test_policy_document_unique_by_source_and_url_hash
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/models/policy_document.py backend/app/models/policy_document_attachment.py backend/app/models/__init__.py backend/alembic/versions/20260331_0005_policy_documents.py backend/tests/test_policy_models.py
git commit -m "feat: 新增政策文档领域模型与迁移"
```

### Task 2: 增加政策同步配置与 Provider 协议

**Files:**
- Modify: `backend/app/core/settings.py`
- Create: `backend/app/integrations/policy_provider.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `backend/tests/test_settings.py`
- Test: `backend/tests/test_policy_provider.py`

**Step 1: Write the failing test**

```python
def test_settings_policy_provider_defaults():
    settings = Settings(_env_file=None)
    assert settings.policy_sync_enabled is True
    assert settings.policy_source_timeout_seconds == 8
```

**Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_settings.py::test_settings_policy_provider_defaults
```

Expected: FAIL with missing settings field

**Step 3: Write minimal implementation**

```python
class PolicyProvider(Protocol):
    # Provider 只负责抓取和归一化原始数据，不负责数据库写入。
    async def fetch_documents(self, *, now: datetime) -> list[PolicyDocumentSeed]: ...
```

建议新增配置：

- `POLICY_SYNC_ENABLED`
- `POLICY_SYNC_LOOKBACK_DAYS`
- `POLICY_SOURCE_TIMEOUT_SECONDS`
- `POLICY_SOURCE_MAX_ITEMS_PER_PROVIDER`
- `POLICY_SYNC_MAX_CONCURRENT_REQUESTS`
- `POLICY_PROVIDER_GOV_CN_ENABLED`
- `POLICY_PROVIDER_NPC_ENABLED`
- `POLICY_PROVIDER_PBC_ENABLED`
- `POLICY_PROVIDER_CSRC_ENABLED`
- `POLICY_PROVIDER_NDRC_ENABLED`
- `POLICY_PROVIDER_MIIT_ENABLED`

**Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_settings.py tests/test_policy_provider.py
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/core/settings.py backend/app/integrations/policy_provider.py .env.example README.md backend/tests/test_settings.py backend/tests/test_policy_provider.py
git commit -m "feat: 增加政策同步配置与 Provider 协议"
```

### Task 3: 实现第一批官方政策 Provider

**Files:**
- Create: `backend/app/integrations/policy_providers/gov_cn_provider.py`
- Create: `backend/app/integrations/policy_providers/npc_provider.py`
- Create: `backend/app/integrations/policy_providers/pbc_provider.py`
- Create: `backend/app/integrations/policy_providers/csrc_provider.py`
- Create: `backend/app/integrations/policy_providers/ndrc_provider.py`
- Create: `backend/app/integrations/policy_providers/miit_provider.py`
- Create: `backend/app/integrations/policy_provider_registry.py`
- Test: `backend/tests/test_policy_providers.py`

**Step 1: Write the failing tests**

```python
async def test_gov_cn_provider_maps_title_and_url():
    # 官方源字段不统一，Provider 必须先归一化为统一种子结构。
    ...

async def test_pbc_provider_extracts_published_at_and_authority():
    ...
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_providers.py
```

Expected: FAIL with missing provider module or wrong mapping

**Step 3: Write minimal implementation**

```python
class GovCnPolicyProvider:
    # 优先抓列表页和详情页的结构化字段，减少对正文正则猜测的依赖。
    async def fetch_documents(self, *, now: datetime) -> list[PolicyDocumentSeed]:
        ...
```

Provider 输出要求：

- 标题必须存在
- URL 必须存在
- 发布时间尽量转为 UTC
- 发文机关缺失时至少给出 `source`
- 附件链接独立输出，不塞进正文摘要

**Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_providers.py
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/integrations/policy_providers backend/app/integrations/policy_provider_registry.py backend/tests/test_policy_providers.py
git commit -m "feat: 接入第一批官方政策 Provider"
```

### Task 4: 实现政策归一化、主题分类与去重服务

**Files:**
- Create: `backend/app/services/policy_normalization_service.py`
- Create: `backend/app/services/policy_dedup_service.py`
- Test: `backend/tests/test_policy_normalization_service.py`
- Test: `backend/tests/test_policy_dedup_service.py`

**Step 1: Write the failing tests**

```python
def test_normalize_policy_document_assigns_macro_topic():
    # 归一化后必须生成统一 macro_topic，供 impact-map 与分析链路复用。
    ...

def test_dedup_policy_documents_prefers_official_text_over_short_summary():
    ...
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_normalization_service.py tests/test_policy_dedup_service.py
```

Expected: FAIL

**Step 3: Write minimal implementation**

```python
def normalize_policy_seed(seed: PolicyDocumentSeed) -> PolicyDocumentNormalized:
    # 关键流程：将发文机关、文号、主题、行业标签统一成仓库可消费的稳定字段。
    ...
```

分类建议：

- `monetary_policy`
- `regulation_policy`
- `industrial_policy`
- `fiscal_tax_policy`
- `energy_policy`
- `capital_market_policy`
- `other`

**Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_normalization_service.py tests/test_policy_dedup_service.py
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/policy_normalization_service.py backend/app/services/policy_dedup_service.py backend/tests/test_policy_normalization_service.py backend/tests/test_policy_dedup_service.py
git commit -m "feat: 增加政策归一化与去重服务"
```

### Task 5: 实现政策持久化仓储与统一同步服务

**Files:**
- Create: `backend/app/services/policy_repository.py`
- Create: `backend/app/services/policy_sync_service.py`
- Create: `backend/scripts/sync_policy_documents.py`
- Test: `backend/tests/test_policy_repository.py`
- Test: `backend/tests/test_policy_sync_service.py`
- Test: `backend/tests/test_policy_sync_job_integration.py`

**Step 1: Write the failing tests**

```python
async def test_upsert_policy_documents_updates_existing_row_without_duplication():
    ...

async def test_policy_sync_service_records_job_metrics():
    ...
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_repository.py tests/test_policy_sync_service.py tests/test_policy_sync_job_integration.py
```

Expected: FAIL

**Step 3: Write minimal implementation**

```python
async def sync_policy_documents(
    session: AsyncSession,
    *,
    trigger_source: str,
    force_refresh: bool,
) -> dict[str, object]:
    # 关键流程：同步服务统一调度 Provider、归一化、去重、入库和任务统计。
    ...
```

要求：

- 每次同步必须记录 `system_job_runs(job_type='policy_sync')`
- `metrics_json` 至少包含：
  - `provider_count`
  - `raw_count`
  - `normalized_count`
  - `inserted_count`
  - `updated_count`
  - `deduped_count`
  - `failed_provider_count`

**Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_repository.py tests/test_policy_sync_service.py tests/test_policy_sync_job_integration.py
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/policy_repository.py backend/app/services/policy_sync_service.py backend/scripts/sync_policy_documents.py backend/tests/test_policy_repository.py backend/tests/test_policy_sync_service.py backend/tests/test_policy_sync_job_integration.py
git commit -m "feat: 落地政策同步服务与任务接入"
```

### Task 6: 将政策文档投影到现有 `news_events` 链路

**Files:**
- Create: `backend/app/services/policy_projection_service.py`
- Modify: `backend/app/services/news_mapper_service.py`
- Modify: `backend/app/services/news_repository.py`
- Modify: `backend/app/api/routes/news.py`
- Modify: `backend/app/integrations/policy_gateway.py`
- Test: `backend/tests/test_policy_projection_service.py`
- Test: `backend/tests/test_news_routes.py`

**Step 1: Write the failing tests**

```python
async def test_policy_documents_project_to_news_events_for_policy_scope():
    ...

async def test_news_policy_route_reads_projected_policy_documents():
    ...
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_projection_service.py tests/test_news_routes.py -k "policy"
```

Expected: FAIL

**Step 3: Write minimal implementation**

```python
async def project_policy_documents_to_news_events(
    session: AsyncSession,
    *,
    documents: list[PolicyDocument],
    fetched_at: datetime,
    batch_id: str | None,
) -> None:
    # 兼容策略：政策文档是主数据，news_events 只保留分析与热点链路所需最小投影。
    ...
```

兼容要求：

- `GET /api/news/policy` 仍可用
- `GET /api/news/events?scope=policy` 能查询到政策投影事件
- `impact-map` 与 `analysis` 继续消费 `news_events`

**Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_projection_service.py tests/test_news_routes.py -k "policy"
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/policy_projection_service.py backend/app/services/news_mapper_service.py backend/app/services/news_repository.py backend/app/api/routes/news.py backend/app/integrations/policy_gateway.py backend/tests/test_policy_projection_service.py backend/tests/test_news_routes.py
git commit -m "feat: 打通政策文档到新闻事件兼容投影"
```

### Task 7: 新增政策查询 API 与后台同步入口

**Files:**
- Create: `backend/app/api/routes/policy.py`
- Create: `backend/app/schemas/policy.py`
- Modify: `backend/app/api/routes/admin.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_policy_routes.py`
- Test: `backend/tests/test_admin_policy_routes.py`

**Step 1: Write the failing tests**

```python
def test_policy_documents_route_supports_authority_and_keyword_filters():
    ...

def test_admin_policy_sync_route_creates_policy_sync_job():
    ...
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_routes.py tests/test_admin_policy_routes.py
```

Expected: FAIL

**Step 3: Write minimal implementation**

```python
@router.get("/policy/documents", response_model=PolicyDocumentPageResponse)
async def list_policy_documents(...):
    # 关键流程：优先支持检索和筛选，详情正文单独走详情接口，避免列表接口过重。
    ...
```

接口建议：

- `GET /api/policy/documents`
- `GET /api/policy/documents/{document_id}`
- `GET /api/policy/filters`
- `POST /api/admin/policy/sync`

**Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_routes.py tests/test_admin_policy_routes.py
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/api/routes/policy.py backend/app/schemas/policy.py backend/app/api/routes/admin.py backend/app/main.py backend/tests/test_policy_routes.py backend/tests/test_admin_policy_routes.py
git commit -m "feat: 增加政策查询接口与后台同步入口"
```

### Task 8: 新增前端政策中心与后台联动

**Files:**
- Create: `frontend/src/api/policy.ts`
- Create: `frontend/src/api/policy.test.ts`
- Create: `frontend/src/views/PolicyDocumentsView.vue`
- Create: `frontend/src/views/PolicyDocumentsView.test.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/views/AdminConsoleView.vue`
- Modify: `frontend/src/views/AdminConsoleView.test.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Step 1: Write the failing tests**

```typescript
test('renders policy document list with filters', async () => {
  // 政策中心至少要能展示列表、筛选和详情入口。
})
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/api/policy.test.ts src/views/PolicyDocumentsView.test.ts
```

Expected: FAIL

**Step 3: Write minimal implementation**

```typescript
export const policyApi = {
  async getDocuments(params: PolicyQuery) {
    // 关键流程：在 API 层统一完成分页与筛选参数拼接，避免视图层散落兼容逻辑。
    ...
  },
}
```

页面能力：

- 列表
- 筛选
- 关键词搜索
- 详情抽屉
- 原文跳转
- 附件展示
- 后台入口可手动触发同步

**Step 4: Run tests to verify they pass**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/api/policy.test.ts src/views/PolicyDocumentsView.test.ts src/views/AdminConsoleView.test.ts
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add frontend/src/api/policy.ts frontend/src/api/policy.test.ts frontend/src/views/PolicyDocumentsView.vue frontend/src/views/PolicyDocumentsView.test.ts frontend/src/router/index.ts frontend/src/App.vue frontend/src/views/AdminConsoleView.vue frontend/src/views/AdminConsoleView.test.ts frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts
git commit -m "feat: 增加前端政策中心与后台联动"
```

### Task 9: 将政策数据接入热点页、分析工作台与个股研究链路

**Files:**
- Modify: `backend/app/services/analysis_service.py`
- Modify: `backend/app/services/analysis_event_selection_service.py`
- Modify: `backend/app/api/routes/news.py`
- Modify: `frontend/src/api/news.ts`
- Modify: `frontend/src/views/HotNewsView.vue`
- Modify: `frontend/src/views/AnalysisWorkbenchView.vue`
- Modify: `frontend/src/views/StockDetailView.vue`
- Test: `backend/tests/test_analysis_service.py`
- Test: `frontend/src/views/HotNewsView.test.ts`
- Test: `frontend/src/views/AnalysisWorkbenchView.test.ts`
- Test: `frontend/src/views/StockDetailView.test.ts`

**Step 1: Write the failing tests**

```python
def test_analysis_summary_marks_policy_document_sources():
    ...
```

```typescript
test('renders related policy documents in hot news impact panel', async () => {
  ...
})
```

**Step 2: Run tests to verify they fail**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_analysis_service.py -k "policy"

Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/views/HotNewsView.test.ts src/views/AnalysisWorkbenchView.test.ts src/views/StockDetailView.test.ts
```

Expected: FAIL

**Step 3: Write minimal implementation**

```python
def map_policy_projection_to_analysis_source(...):
    # 使用链路必须能区分“政策原文”和“政策新闻”，避免分析结果混淆证据等级。
    ...
```

最小目标：

- 热点页能显示“相关政策”
- 分析工作台能展示政策类引用
- 个股详情可看到相关政策

**Step 4: Run tests to verify they pass**

Run the same commands as Step 2

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/analysis_service.py backend/app/services/analysis_event_selection_service.py backend/app/api/routes/news.py frontend/src/api/news.ts frontend/src/views/HotNewsView.vue frontend/src/views/AnalysisWorkbenchView.vue frontend/src/views/StockDetailView.vue backend/tests/test_analysis_service.py frontend/src/views/HotNewsView.test.ts frontend/src/views/AnalysisWorkbenchView.test.ts frontend/src/views/StockDetailView.test.ts
git commit -m "feat: 打通政策数据到热点与分析使用链路"
```

### Task 10: 可观测性、回归验证与文档收尾

**Files:**
- Modify: `backend/app/services/policy_sync_service.py`
- Modify: `backend/app/api/routes/health.py`
- Create: `docs/architecture/policy-data-flow.md`
- Modify: `README.md`
- Modify: `PROGRESS.md`
- Test: `backend/tests/test_policy_sync_service.py`

**Step 1: Write the failing test**

```python
def test_policy_sync_service_emits_source_level_metrics():
    ...
```

**Step 2: Run test to verify it fails**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_sync_service.py -k "metrics"
```

Expected: FAIL

**Step 3: Write minimal implementation**

```python
metrics = {
    "provider_stats": [...],
    "inserted_count": inserted_count,
    "updated_count": updated_count,
    "deduped_count": deduped_count,
}
```

文档必须补齐：

- 政策数据流架构图
- 政策同步命令
- Provider 清单
- 兼容接口说明
- 运维排障要点

**Step 4: Run verification**

Run:

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run pytest -q tests/test_policy_sync_service.py tests/test_policy_routes.py tests/test_admin_policy_routes.py

Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/api/policy.test.ts src/views/PolicyDocumentsView.test.ts
```

Expected: PASS

**Step 5: Commit**

```powershell
Set-Location 'E:\Development\Project\StockProject'
git add backend/app/services/policy_sync_service.py backend/app/api/routes/health.py docs/architecture/policy-data-flow.md README.md PROGRESS.md backend/tests/test_policy_sync_service.py
git commit -m "docs: 完善政策数据全链路文档与观测说明"
```

---

## 7. 关键文件改动总览

### 7.1 Backend - Create

- `backend/app/models/policy_document.py`
- `backend/app/models/policy_document_attachment.py`
- `backend/app/integrations/policy_provider.py`
- `backend/app/integrations/policy_provider_registry.py`
- `backend/app/integrations/policy_providers/gov_cn_provider.py`
- `backend/app/integrations/policy_providers/npc_provider.py`
- `backend/app/integrations/policy_providers/pbc_provider.py`
- `backend/app/integrations/policy_providers/csrc_provider.py`
- `backend/app/integrations/policy_providers/ndrc_provider.py`
- `backend/app/integrations/policy_providers/miit_provider.py`
- `backend/app/services/policy_normalization_service.py`
- `backend/app/services/policy_dedup_service.py`
- `backend/app/services/policy_repository.py`
- `backend/app/services/policy_sync_service.py`
- `backend/app/services/policy_projection_service.py`
- `backend/app/api/routes/policy.py`
- `backend/app/schemas/policy.py`
- `backend/scripts/sync_policy_documents.py`
- `backend/alembic/versions/20260331_0005_policy_documents.py`

### 7.2 Backend - Modify

- `backend/app/models/__init__.py`
- `backend/app/core/settings.py`
- `backend/app/main.py`
- `backend/app/api/routes/admin.py`
- `backend/app/api/routes/news.py`
- `backend/app/integrations/policy_gateway.py`
- `backend/app/services/news_mapper_service.py`
- `backend/app/services/news_repository.py`
- `backend/app/services/analysis_service.py`
- `backend/app/services/analysis_event_selection_service.py`
- `backend/app/api/routes/health.py`

### 7.3 Frontend - Create

- `frontend/src/api/policy.ts`
- `frontend/src/api/policy.test.ts`
- `frontend/src/views/PolicyDocumentsView.vue`
- `frontend/src/views/PolicyDocumentsView.test.ts`

### 7.4 Frontend - Modify

- `frontend/src/router/index.ts`
- `frontend/src/App.vue`
- `frontend/src/api/news.ts`
- `frontend/src/views/HotNewsView.vue`
- `frontend/src/views/AnalysisWorkbenchView.vue`
- `frontend/src/views/StockDetailView.vue`
- `frontend/src/views/AdminConsoleView.vue`
- `frontend/src/i18n/locales/zh-CN.ts`
- `frontend/src/i18n/locales/en-US.ts`

### 7.5 Tests - Create/Modify

- `backend/tests/test_policy_models.py`
- `backend/tests/test_policy_provider.py`
- `backend/tests/test_policy_providers.py`
- `backend/tests/test_policy_normalization_service.py`
- `backend/tests/test_policy_dedup_service.py`
- `backend/tests/test_policy_repository.py`
- `backend/tests/test_policy_sync_service.py`
- `backend/tests/test_policy_sync_job_integration.py`
- `backend/tests/test_policy_projection_service.py`
- `backend/tests/test_policy_routes.py`
- `backend/tests/test_admin_policy_routes.py`
- `frontend/src/api/policy.test.ts`
- `frontend/src/views/PolicyDocumentsView.test.ts`

---

## 8. 测试与验收清单

### 8.1 后端验收

必须至少通过：

```powershell
Set-Location 'E:\Development\Project\StockProject\backend'
uv run alembic upgrade head
uv run pytest -q tests/test_policy_models.py tests/test_policy_providers.py tests/test_policy_repository.py tests/test_policy_sync_service.py tests/test_policy_routes.py tests/test_admin_policy_routes.py
uv run pytest -q tests/test_news_routes.py -k "policy"
uv run pytest -q tests/test_analysis_service.py -k "policy"
```

### 8.2 前端验收

必须至少通过：

```powershell
Set-Location 'E:\Development\Project\StockProject\frontend'
npm run test -- --run src/api/policy.test.ts src/views/PolicyDocumentsView.test.ts src/views/HotNewsView.test.ts src/views/AnalysisWorkbenchView.test.ts src/views/StockDetailView.test.ts
npm run build
```

### 8.3 手工联调验收

必须手工验证：

1. 管理员可手动触发政策同步
2. `/api/policy/documents` 可按机构、类别、关键词查询
3. `/api/policy/documents/{id}` 能看到正文和附件
4. `/api/news/policy` 仍可正常返回政策事件
5. 热点页可看到相关政策
6. 分析工作台能区分政策原文引用
7. 后台任务中心能看到 `policy_sync` 任务

---

## 9. 里程碑与交付顺序

### Milestone 1：政策主数据最小闭环

- Task 1
- Task 2
- Task 3
- Task 4
- Task 5

交付结果：

- 可抓取官方政策源
- 可入库 `policy_documents`
- 后台任务中心能看到同步结果

### Milestone 2：兼容旧链路并开放 API

- Task 6
- Task 7

交付结果：

- `/api/news/policy` 兼容
- `/api/policy/*` 可用

### Milestone 3：产品化使用

- Task 8
- Task 9
- Task 10

交付结果：

- 前端政策中心上线
- 热点/分析/个股链路可使用政策数据
- 文档与运维说明完整

---

## 10. 风险与应对

### 风险 1：官方站点结构不统一

应对：

- Provider 必须逐站点定制
- 统一输出 `PolicyDocumentSeed`
- provider 单测使用固定 fixture，避免线上结构变动直接打崩全链路

### 风险 2：同一政策多处发布、重复严重

应对：

- 以 `source_document_id` + `url_hash` + `document_no` 组合去重
- 归一化时优先保留正文更完整的版本

### 风险 3：抓取过于频繁被限流

应对：

- 增加 provider 并发上限与 lookback 窗口
- 先日级 / 半日级同步，不做分钟级刷新

### 风险 4：兼容旧链路时出现双写不一致

应对：

- 明确 `policy_documents` 是主数据
- `news_events` 只做投影
- 投影由单独服务统一生成，不允许各 Provider 直接写 `news_events`

---

## 11. 完成定义

达到以下条件才算本计划完成：

- 至少 6 个第一阶段官方政策源已接入
- `policy_documents` / `policy_document_attachments` 已上线
- 后台可触发并查看 `policy_sync`
- `/api/policy/documents` / detail / filters 可用
- `/api/news/policy` 继续可用且数据来自新政策链路
- 热点页 / 分析工作台 / 个股详情至少一处已消费政策数据
- 相关后端与前端回归测试通过
- README、架构文档、环境说明已更新

---

**Plan complete and saved to `docs/plans/2026-03-31-stockproject-policy-data-full-chain-implementation-plan.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
