import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import StockDetailView from './StockDetailView.vue'
import { i18n, setAppLocale } from '../i18n'


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
})
