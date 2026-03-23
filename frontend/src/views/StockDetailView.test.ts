import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import StockDetailView from './StockDetailView.vue'
import { i18n, setAppLocale } from '../i18n'
import { watchlistApi } from '../api/watchlist'
import { useAuthStore } from '../stores/auth'


const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})


describe('StockDetailView', () => {
  it('loads stock detail and recent daily data', async () => {
    const fetchMock = vi
      .fn()
        .mockResolvedValueOnce(
          jsonResponse({
            instrument: {
              ts_code: '600000.SH',
              symbol: '600000',
              name: '浦发银行',
              fullname: '上海浦东发展银行股份有限公司',
              area: '上海',
              industry: '银行',
              market: '主板',
              exchange: 'SSE',
              list_status: 'L',
              list_date: '1999-11-10',
              delist_date: null,
              is_hs: 'H',
            },
            latest_snapshot: {
              ts_code: '600000.SH',
              trade_date: '2026-03-03',
              open: 8.1,
              high: 8.3,
              low: 8.0,
              close: 7.9,
              pre_close: 8.05,
              change: -0.15,
              pct_chg: -1.88,
              vol: 654321,
              amount: 321098,
              turnover_rate: 1.8,
              volume_ratio: 1.1,
              pe: 5.8,
              pb: 0.62,
              total_mv: 2000000,
              circ_mv: 1800000,
            },
          }),
        )
        .mockResolvedValueOnce(
          jsonResponse([
            {
              ts_code: '600000.SH',
              trade_date: '2026-03-03',
              open: 8.1,
              high: 8.3,
              low: 8.0,
              close: 8.25,
              pre_close: 8.05,
              change: 0.2,
              pct_chg: 2.48,
              vol: 654321,
              amount: 321098,
              turnover_rate: null,
              volume_ratio: null,
              pe: null,
              pb: null,
              total_mv: null,
              circ_mv: null,
            },
            {
              ts_code: '600000.SH',
              trade_date: '2026-03-02',
              open: 8.0,
              high: 8.2,
              low: 7.9,
              close: 8.05,
              pre_close: 7.95,
              change: 0.1,
              pct_chg: 1.26,
              vol: 520000,
              amount: 280000,
              turnover_rate: null,
              volume_ratio: null,
              pe: null,
              pb: null,
              total_mv: null,
              circ_mv: null,
            },
          ]),
        )
        .mockResolvedValueOnce(
          jsonResponse([
            {
              ts_code: '600000.SH',
              trade_date: '2026-03-03',
              adj_factor: 2.0,
            },
            {
              ts_code: '600000.SH',
              trade_date: '2026-03-02',
              adj_factor: 1.9,
            },
          ]),
        )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/stocks/:tsCode', component: StockDetailView }],
    })
    await router.push('/stocks/600000.SH')
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('浦发银行')
    expect(wrapper.text()).not.toContain('600000.SH')
    expect(wrapper.text()).toContain('上海浦东发展银行股份有限公司')
    expect(wrapper.text()).toContain('8.25')
    expect(wrapper.text()).toContain('2026-03-03')
    expect(wrapper.find('[data-testid="kline-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="kline-period-daily"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="kline-period-weekly"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="kline-period-monthly"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="kline-adjust-none"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="kline-adjust-qfq"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="kline-adjust-hfq"]').exists()).toBe(true)

    const latestClose = wrapper.get('[data-testid="latest-close-value"]').text()
    const latestChange = wrapper.get('[data-testid="latest-change-value"]').text()
    expect(latestClose).toBe('8.25')
    expect(latestChange).toBe('+2.48%')

    expect(wrapper.find('[data-testid="kline-tooltip"]').exists()).toBe(false)
    const interactiveLayer = wrapper.get('[data-testid="kline-interaction-layer"]')
    await interactiveLayer.trigger('mousemove', { clientX: 200, clientY: 120 })
    await flushPromises()
    expect(wrapper.find('[data-testid="kline-tooltip"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('2026-03-03')
    expect(wrapper.text()).toContain('¥8.25')

    const dailyRequest = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(dailyRequest[0]).toContain('/api/stocks/600000.SH/daily?')
    expect(dailyRequest[0]).toContain('limit=60')
    expect(dailyRequest[0]).toContain('period=daily')
    expect(dailyRequest[0]).not.toContain('adjust=')

    const newsRequest = fetchMock.mock.calls[3] as [string, RequestInit]
    expect(newsRequest[0]).toContain('/api/stocks/600000.SH/news?')

    const adjFactorRequest = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(adjFactorRequest[0]).toContain('/api/stocks/600000.SH/adj-factor?')
    expect(adjFactorRequest[0]).toContain('start_date=20260302')
    expect(adjFactorRequest[0]).toContain('end_date=20260303')

    const mainPanel = wrapper.find('[data-testid="stock-detail-main-panel"]')
    const newsPanel = wrapper.find('[data-testid="stock-detail-news-panel"]')
    expect(mainPanel.exists()).toBe(true)
    expect(newsPanel.exists()).toBe(true)
  })

  it('shows stock-related news section and requests stock news endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.0,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            symbol: '600000',
            title: '浦发银行发布业绩快报',
            summary: '净利润同比增长',
            published_at: '2026-03-03T09:12:00',
            url: 'https://finance.example.com/a/1',
            publisher: '东方财富',
            source: 'eastmoney_stock',
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/stocks/:tsCode', component: StockDetailView }],
    })
    await router.push('/stocks/600000.SH')
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('相关新闻')
    expect(wrapper.text()).toContain('浦发银行发布业绩快报')

    const newsRequest = fetchMock.mock.calls[3] as [string, RequestInit]
    expect(newsRequest[0]).toContain('/api/stocks/600000.SH/news')

    await wrapper.get('[data-testid="kline-period-weekly"]').trigger('click')
    await flushPromises()

    const newsRequests = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes('/api/stocks/600000.SH/news'),
    )
    expect(newsRequests).toHaveLength(1)
  })

  it('renders kline panel before related news section', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.0,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            symbol: '600000',
            title: '浦发银行发布业绩快报',
            summary: '净利润同比增长',
            published_at: '2026-03-03T09:12:00',
            url: 'https://finance.example.com/a/1',
            publisher: '东方财富',
            source: 'eastmoney_stock',
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/stocks/:tsCode', component: StockDetailView }],
    })
    await router.push('/stocks/600000.SH')
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const html = wrapper.html()
    expect(html.indexOf('data-testid="kline-chart"')).toBeGreaterThan(-1)
    expect(html.indexOf('浦发银行发布业绩快报')).toBeGreaterThan(-1)
    expect(html.indexOf('data-testid="kline-chart"')).toBeLessThan(html.indexOf('浦发银行发布业绩快报'))
  })

  it('does not refetch related news when switching kline period', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.0,
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.6,
            low: 8.0,
            close: 8.4,
            pre_close: 8.05,
            change: 0.35,
            pct_chg: 4.35,
            vol: 700000,
            amount: 350000,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.1,
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/stocks/:tsCode', component: StockDetailView }],
    })
    await router.push('/stocks/600000.SH')
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="kline-period-weekly"]').trigger('click')
    await flushPromises()

    const newsRequests = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes('/api/stocks/600000.SH/news'),
    )
    expect(newsRequests).toHaveLength(1)
  })

  it('navigates to analysis workbench from stock detail action', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.0,
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/stocks/:tsCode', component: StockDetailView },
        { path: '/analysis', component: { template: '<div>analysis</div>' } },
      ],
    })
    await router.push('/stocks/600000.SH')
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const analysisButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('分析此股票'))
    expect(analysisButton).toBeDefined()

    await analysisButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/analysis')
    expect(router.currentRoute.value.query.ts_code).toBe('600000.SH')
    expect(router.currentRoute.value.query.source).toBe('stock_detail')
  })

  it('renders hot-news context and preserves event query when entering analysis', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.0,
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/stocks/:tsCode', component: StockDetailView },
        { path: '/analysis', component: { template: '<div>analysis</div>' } },
      ],
    })
    await router.push({
      path: '/stocks/600000.SH',
      query: {
        source: 'hot_news',
        topic: 'commodity_supply',
        event_id: 'evt-hot-1',
        event_title: '国际油价高位震荡',
      },
    })
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('国际油价高位震荡')
    expect(wrapper.text()).toContain('大宗供给')

    const analysisButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('分析此股票'))
    expect(analysisButton).toBeDefined()

    await analysisButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/analysis')
    expect(router.currentRoute.value.query.topic).toBe('commodity_supply')
    expect(router.currentRoute.value.query.event_id).toBe('evt-hot-1')
    expect(router.currentRoute.value.query.event_title).toBe('国际油价高位震荡')
    expect(router.currentRoute.value.query.source).toBe('hot_news')
  })

  it('toggles watchlist state for authenticated users', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.0,
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })
    const createSpy = vi.spyOn(watchlistApi, 'createWatchlistItem').mockResolvedValue({
      id: 'watch-1',
      ts_code: '600000.SH',
      hourly_sync_enabled: true,
      daily_analysis_enabled: true,
      web_search_enabled: false,
      last_hourly_sync_at: null,
      last_daily_analysis_at: null,
      created_at: '2026-03-23T08:00:00Z',
      updated_at: '2026-03-23T08:00:00Z',
      instrument: null,
      latest_report: null,
    })
    const deleteSpy = vi
      .spyOn(watchlistApi, 'deleteWatchlistItem')
      .mockResolvedValue({ message: 'ok' })

    setAppLocale('zh-CN')
    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.accessToken = 'token'
    authStore.user = {
      id: 'user-1',
      username: 'watcher',
      email: 'watcher@example.com',
      is_active: true,
      user_level: 'user',
    }
    authStore.initialized = true

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/stocks/:tsCode', component: StockDetailView }],
    })
    await router.push('/stocks/600000.SH')
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const firstAction = wrapper
      .findAll('button')
      .find((item) => item.text().includes('加入关注'))
    expect(firstAction).toBeDefined()
    await firstAction!.trigger('click')
    await flushPromises()

    expect(createSpy).toHaveBeenCalledWith('token', { ts_code: '600000.SH' })
    expect(wrapper.text()).toContain('移出关注')

    const secondAction = wrapper
      .findAll('button')
      .find((item) => item.text().includes('移出关注'))
    expect(secondAction).toBeDefined()
    await secondAction!.trigger('click')
    await flushPromises()

    expect(deleteSpy).toHaveBeenCalledWith('token', '600000.SH')
    expect(wrapper.text()).toContain('加入关注')
  })

  it('redirects to login when unauthenticated user tries to add watchlist', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          instrument: {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            area: '上海',
            industry: '银行',
            market: '主板',
            exchange: 'SSE',
            list_status: 'L',
            list_date: '1999-11-10',
            delist_date: null,
            is_hs: 'H',
          },
          latest_snapshot: null,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            open: 8.1,
            high: 8.3,
            low: 8.0,
            close: 8.25,
            pre_close: 8.05,
            change: 0.2,
            pct_chg: 2.48,
            vol: 654321,
            amount: 321098,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            trade_date: '2026-03-03',
            adj_factor: 2.0,
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.initialized = true

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/stocks/:tsCode', component: StockDetailView },
        { path: '/login', component: { template: '<div>login</div>' } },
      ],
    })
    await router.push('/stocks/600000.SH')
    await router.isReady()

    const wrapper = mount(StockDetailView, {
      global: {
        plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const watchlistButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('登录后加入关注'))
    expect(watchlistButton).toBeDefined()

    await watchlistButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/stocks/600000.SH')
  })
})
