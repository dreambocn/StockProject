# News Ingestion And Display Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete multi-source news collection and display flow where dashboard shows global hot news and stock detail only shows stock-related news.

**Architecture:** Backend adds a dedicated AkShare gateway, normalized mappers, and two read APIs (`/api/news/hot`, `/api/stocks/{ts_code}/news`). Frontend adds a hot news page and navigation entry, while stock detail renders only related news from the stock-scoped endpoint. Data source boundaries are strict: global news never mixes into stock detail.

**Tech Stack:** FastAPI, Pydantic, Redis cache (optional), AkShare, Vue 3, TypeScript, Vue Router, Vitest.

---

## Chunk 1: Backend APIs and data normalization

### Task 1: Add AkShare news gateway

**Files:**
- Create: `backend/app/integrations/akshare_gateway.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_news_routes.py`

- [ ] **Step 1: Write failing test for hot news source call path**

```python
def test_hot_news_route_calls_akshare_gateway_once(client, monkeypatch):
    called = {"count": 0}

    def fake_fetch_hot_news():
        called["count"] += 1
        return []

    monkeypatch.setattr("app.integrations.akshare_gateway.fetch_hot_news", fake_fetch_hot_news)
    resp = client.get("/api/news/hot")
    assert resp.status_code == 200
    assert called["count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest -q tests/test_news_routes.py::test_hot_news_route_calls_akshare_gateway_once`
Expected: FAIL with import or missing route/function error.

- [ ] **Step 3: Add minimal gateway implementation**

```python
def fetch_hot_news() -> list[dict[str, object]]:
    import akshare as ak
    df = ak.stock_info_global_em()
    return df.to_dict("records")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest -q tests/test_news_routes.py::test_hot_news_route_calls_akshare_gateway_once`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/integrations/akshare_gateway.py backend/tests/test_news_routes.py
git commit -m "feat: add akshare news gateway for hot news endpoint"
```

### Task 2: Add normalized schemas and mapper service

**Files:**
- Create: `backend/app/schemas/news.py`
- Create: `backend/app/services/news_mapper_service.py`
- Test: `backend/tests/test_news_routes.py`

- [ ] **Step 1: Write failing test for response field normalization**

```python
def test_hot_news_response_contains_normalized_fields(client, monkeypatch):
    monkeypatch.setattr(
        "app.integrations.akshare_gateway.fetch_hot_news",
        lambda: [{"标题": "x", "摘要": "y", "发布时间": "2024-01-01 09:00:00", "链接": "http://a"}],
    )
    payload = client.get("/api/news/hot").json()
    assert payload[0]["title"] == "x"
    assert payload[0]["published_at"] == "2024-01-01T09:00:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest -q tests/test_news_routes.py::test_hot_news_response_contains_normalized_fields`
Expected: FAIL because fields are not normalized yet.

- [ ] **Step 3: Implement minimal mapper + schema**

```python
class HotNewsItemResponse(BaseModel):
    title: str
    summary: str | None
    published_at: datetime
    url: str
    source: str = "eastmoney_global"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest -q tests/test_news_routes.py::test_hot_news_response_contains_normalized_fields`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/news.py backend/app/services/news_mapper_service.py backend/tests/test_news_routes.py
git commit -m "feat: normalize hot and stock news schema fields"
```

### Task 3: Add hot news route

**Files:**
- Create: `backend/app/api/routes/news.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_news_routes.py`

- [ ] **Step 1: Write failing test for `/api/news/hot` route success and error path**

```python
def test_get_hot_news_success(client):
    resp = client.get("/api/news/hot")
    assert resp.status_code == 200

def test_get_hot_news_upstream_error_returns_503(client, monkeypatch):
    monkeypatch.setattr("app.integrations.akshare_gateway.fetch_hot_news", lambda: (_ for _ in ()).throw(RuntimeError("upstream")))
    resp = client.get("/api/news/hot")
    assert resp.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest -q tests/test_news_routes.py -k hot_news`
Expected: FAIL.

- [ ] **Step 3: Implement route and register router**

```python
@router.get("/news/hot", response_model=list[HotNewsItemResponse])
async def get_hot_news(limit: int = Query(50, ge=1, le=200)):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest -q tests/test_news_routes.py -k hot_news`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/news.py backend/app/main.py backend/tests/test_news_routes.py
git commit -m "feat: expose hot news api route"
```

### Task 4: Add stock-related news route under stocks API

**Files:**
- Modify: `backend/app/api/routes/stocks.py`
- Test: `backend/tests/test_stock_routes.py`

- [ ] **Step 1: Write failing test for stock-scoped news**

```python
def test_stock_detail_news_only_returns_requested_symbol(client, monkeypatch):
    monkeypatch.setattr("app.integrations.akshare_gateway.fetch_stock_news", lambda symbol: [{"关键词": symbol, "新闻标题": "x"}])
    resp = client.get("/api/stocks/600519.SH/news")
    assert resp.status_code == 200
    assert all(item["symbol"] == "600519" for item in resp.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest -q tests/test_stock_routes.py -k news`
Expected: FAIL.

- [ ] **Step 3: Implement minimal route using ts_code to symbol normalization**

```python
symbol = ts_code.split(".")[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest -q tests/test_stock_routes.py -k news`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/stocks.py backend/tests/test_stock_routes.py
git commit -m "feat: add stock-related news endpoint under stocks api"
```

## Chunk 2: Frontend pages and API integration

### Task 5: Add frontend API clients

**Files:**
- Create: `frontend/src/api/news.ts`
- Modify: `frontend/src/api/stocks.ts`
- Test: `frontend/src/views/HotNewsView.test.ts`

- [ ] **Step 1: Write failing test expecting API client calls**

```ts
it('calls /api/news/hot when loading hot news view', async () => {
  // expect request to /api/news/hot
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/views/HotNewsView.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement minimal API wrappers**

```ts
export const newsApi = {
  getHotNews(limit = 50) {
    return requestJson<HotNewsItem[]>(`/api/news/hot?limit=${limit}`)
  },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/views/HotNewsView.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/news.ts frontend/src/api/stocks.ts frontend/src/views/HotNewsView.test.ts
git commit -m "feat: add frontend api clients for hot and stock news"
```

### Task 6: Add HotNews page and router entry

**Files:**
- Create: `frontend/src/views/HotNewsView.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Test: `frontend/src/router/index.test.ts`

- [ ] **Step 1: Write failing route/nav tests**

```ts
it('registers /news/hot route', () => {
  // expect route exists
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/router/index.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement route, nav link, and view page**

```ts
{ path: '/news/hot', name: 'hot-news', component: () => import('../views/HotNewsView.vue') }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/router/index.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/HotNewsView.vue frontend/src/router/index.ts frontend/src/App.vue frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts frontend/src/router/index.test.ts
git commit -m "feat: add hot news page and navigation entry"
```

### Task 7: Add stock-related news section to StockDetail page only

**Files:**
- Modify: `frontend/src/views/StockDetailView.vue`
- Test: `frontend/src/views/StockDetailView.test.ts`

- [ ] **Step 1: Write failing test for related-news section**

```ts
it('shows only stock-related news in stock detail', async () => {
  // mock getStockRelatedNews and assert render
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/views/StockDetailView.test.ts -t "related news"`
Expected: FAIL.

- [ ] **Step 3: Implement minimal UI section and call getStockRelatedNews(tsCode)**

```ts
const relatedNews = ref<StockRelatedNewsItem[]>([])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/views/StockDetailView.test.ts -t "related news"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/StockDetailView.vue frontend/src/views/StockDetailView.test.ts
git commit -m "feat: display stock-related news in stock detail page"
```

### Task 8: Add dashboard jump entry to hot news page

**Files:**
- Modify: `frontend/src/views/HomeView.vue`
- Test: `frontend/src/views/HomeView.test.ts`

- [ ] **Step 1: Write failing test for hot news jump action**

```ts
it('renders hot news jump action in dashboard header', () => {
  // expect button/link to /news/hot
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/views/HomeView.test.ts -t "hot news jump"`
Expected: FAIL.

- [ ] **Step 3: Implement jump button**

```vue
<router-link to="/news/hot">{{ t('home.hotNews') }}</router-link>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/views/HomeView.test.ts -t "hot news jump"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/HomeView.vue frontend/src/views/HomeView.test.ts
git commit -m "feat: add dashboard jump action to hot news page"
```

## Chunk 3: Verification and project records

### Task 9: Full verification

**Files:**
- Test: `backend/tests/test_news_routes.py`
- Test: `backend/tests/test_stock_routes.py`
- Test: `frontend/src/views/HotNewsView.test.ts`
- Test: `frontend/src/views/StockDetailView.test.ts`

- [ ] **Step 1: Run backend target tests**

Run: `cd backend && uv run pytest -q tests/test_news_routes.py tests/test_stock_routes.py`
Expected: PASS.

- [ ] **Step 2: Run backend full tests**

Run: `cd backend && uv run pytest -q`
Expected: PASS.

- [ ] **Step 3: Run frontend target tests**

Run: `cd frontend && npm run test -- --run src/views/HotNewsView.test.ts src/views/StockDetailView.test.ts`
Expected: PASS.

- [ ] **Step 4: Run frontend full tests and build**

Run: `cd frontend && npm run test -- --run && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit verification-safe changes if needed**

```bash
git add .
git commit -m "test: verify news ingestion and display flow"
```

### Task 10: Record milestone

**Files:**
- Modify: `PROGRESS.md`

- [ ] **Step 1: Add progress entry for hot news + stock-related news split display**
- [ ] **Step 2: Commit milestone log update**

```bash
git add PROGRESS.md docs/plans/2026-03-11-news-ingestion-and-display.md
git commit -m "docs: record news ingestion and display implementation plan"
```

---

## Acceptance checklist

- [ ] Dashboard has a visible jump entry to hot news page.
- [ ] Hot news page shows global hot news from `stock_info_global_em`.
- [ ] Stock detail page only shows related stock news (and stock announcements if enabled).
- [ ] Global hot news is not mixed into stock detail feed.
- [ ] Backend and frontend tests pass.
- [ ] Build succeeds.

---

## Chunk 4: Phase 5 Backlog (Record Only)

### Task 11: Make dynamic candidates actionable from impact panel

**Files:**
- Modify: `frontend/src/views/HotNewsView.vue`
- Modify: `frontend/src/router/index.ts`
- Test: `frontend/src/views/HotNewsView.test.ts`

- [ ] Add click action from `A股动态候选` entry to `/stocks/{ts_code}`.
- [ ] Keep hot-news page context state (selected topic) when navigating away and back.
- [ ] Add test to verify candidate click generates stock-detail route navigation.

### Task 12: Rank candidates by relevance score

**Files:**
- Modify: `backend/app/services/news_mapper_service.py`
- Modify: `backend/app/api/routes/news.py`
- Modify: `backend/app/schemas/news.py`
- Test: `backend/tests/test_news_routes.py`

- [ ] Add server-side relevance score for each dynamic candidate.
- [ ] Score components (MVP):
  - industry keyword exact hit weight
  - name/fullname keyword hit weight
  - topic-priority boost (e.g. `commodity_supply` prefers resources)
- [ ] Sort candidates by score desc before truncating by `candidate_limit`.
- [ ] Expose `relevance_score` in API response and add tests for ordering stability.

### Task 13: Link impact candidates to event-volatility explanation chain

**Files:**
- Modify: `backend/app/api/routes/event_impact.py` (or target event-impact route file)
- Modify: `backend/app/services/event_impact_service.py`
- Modify: `frontend/src/views/StockDetailView.vue`
- Test: `backend/tests/test_event_impact_routes.py`
- Test: `frontend/src/views/StockDetailView.test.ts`

- [ ] Add handoff endpoint/params so hot-news candidate can prefill stock/event context.
- [ ] In stock detail, show a compact “事件-波动解释” block tied to selected topic/event window.
- [ ] Add fallback when event-impact data is unavailable (no crash, empty-state with retry).
- [ ] Add backend/frontend tests for end-to-end handoff behavior.

### Task 14: Verification and release checklist for Phase 5

**Files:**
- Modify: `PROGRESS.md`
- Test: `backend/tests/test_news_routes.py`
- Test: `frontend/src/views/HotNewsView.test.ts`

- [ ] Run backend targeted tests: `cd backend && uv run pytest -q tests/test_news_routes.py`.
- [ ] Run frontend targeted tests: `cd frontend && npm run test -- --run src/views/HotNewsView.test.ts src/views/StockDetailView.test.ts`.
- [ ] Run full verification commands before completion claim:
  - `cd backend && uv run pytest -q`
  - `cd frontend && npm run test -- --run && npm run build`
