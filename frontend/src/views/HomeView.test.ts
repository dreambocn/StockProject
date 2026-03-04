import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import HomeView from './HomeView.vue'
import { i18n, setAppLocale } from '../i18n'

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = []
  static options: IntersectionObserverInit[] = []

  callback: IntersectionObserverCallback

  constructor(callback: IntersectionObserverCallback, options: IntersectionObserverInit = {}) {
    this.callback = callback
    MockIntersectionObserver.instances.push(this)
    MockIntersectionObserver.options.push(options)
  }

  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()

  trigger(isIntersecting: boolean) {
    const entry = { isIntersecting } as IntersectionObserverEntry
    this.callback([entry], this as unknown as IntersectionObserver)
  }
}


const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})


const mountHomeView = async () => {
  setAppLocale('zh-CN')
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: HomeView },
      { path: '/stocks/:tsCode', component: { template: '<div>detail</div>' } },
    ],
  })
  await router.push('/')
  await router.isReady()

  return mount(HomeView, {
    global: {
      plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
    },
  })
}

beforeEach(() => {
  MockIntersectionObserver.instances = []
  MockIntersectionObserver.options = []
  vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0)
    return 1
  })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
})


describe('HomeView', () => {
  it('renders stock list from backend payload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            ts_code: '000001.SZ',
            symbol: '000001',
            name: '平安银行',
            fullname: '平安银行股份有限公司',
            exchange: 'SZSE',
            close: 11.1,
            pct_chg: 1.37,
            trade_date: '2026-03-03',
          },
        ]),
      ),
    )

    const wrapper = await mountHomeView()
    await flushPromises()

    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('平安银行股份有限公司')
    expect(wrapper.text()).toContain('000001')
    expect(wrapper.text()).toContain('11.10')
    expect(wrapper.find('.stock-waterfall').exists()).toBe(true)
    expect(wrapper.find('.stock-card-vertical').exists()).toBe(true)
    expect(wrapper.find('.stock-card-horizontal').exists()).toBe(false)
  })

  it('loads next page when scrolling to bottom', async () => {
    const firstPageStocks = Array.from({ length: 20 }, (_, index) => ({
      ts_code: `${String(index + 1).padStart(6, '0')}.SZ`,
      symbol: String(index + 1).padStart(6, '0'),
      name: index === 0 ? '平安银行' : `测试股票${index + 1}`,
      fullname: index === 0 ? '平安银行股份有限公司' : `测试股票${index + 1}股份有限公司`,
      exchange: 'SZSE',
      close: 10 + index,
      pct_chg: 1,
      trade_date: '2026-03-03',
    }))

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(firstPageStocks),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            exchange: 'SSE',
            close: 8.25,
            pct_chg: 2.48,
            trade_date: '2026-03-03',
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountHomeView()
    await flushPromises()

    expect(MockIntersectionObserver.options[0]).toMatchObject({
      rootMargin: '0px 0px 260px 0px',
      threshold: 0.01,
    })

    const observer = MockIntersectionObserver.instances[0]
    if (!observer) {
      throw new Error('expected intersection observer instance')
    }
    observer.trigger(true)
    await flushPromises()

    const firstRequest = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(firstRequest[0]).toContain('/api/stocks?page=1&page_size=20')

    const secondRequest = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(secondRequest[0]).toContain('/api/stocks?page=2&page_size=20')

    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('浦发银行')
  })

  it('keeps existing cards stable when next page has duplicate ts_code', async () => {
    const firstPageStocks = Array.from({ length: 20 }, (_, index) => ({
      ts_code: `${String(index + 1).padStart(6, '0')}.SZ`,
      symbol: String(index + 1).padStart(6, '0'),
      name: index === 0 ? '平安银行' : `测试股票${index + 1}`,
      fullname: index === 0 ? '平安银行股份有限公司' : `测试股票${index + 1}股份有限公司`,
      exchange: 'SZSE',
      close: index === 0 ? 11.1 : 10 + index,
      pct_chg: 1,
      trade_date: '2026-03-03',
    }))

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(firstPageStocks))
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '000001.SZ',
            symbol: '000001',
            name: '平安银行(重复)',
            fullname: '平安银行股份有限公司(重复)',
            exchange: 'SZSE',
            close: 99.9,
            pct_chg: 9.99,
            trade_date: '2026-03-03',
          },
          {
            ts_code: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            fullname: '上海浦东发展银行股份有限公司',
            exchange: 'SSE',
            close: 8.25,
            pct_chg: 2.48,
            trade_date: '2026-03-03',
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountHomeView()
    await flushPromises()

    const observer = MockIntersectionObserver.instances[0]
    if (!observer) {
      throw new Error('expected intersection observer instance')
    }
    observer.trigger(true)
    await flushPromises()

    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).not.toContain('平安银行(重复)')
    expect(wrapper.text()).toContain('11.10')
    expect(wrapper.text()).not.toContain('99.90')
    expect(wrapper.text()).toContain('浦发银行')
  })

  it('sends keyword when searching stocks', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountHomeView()
    await flushPromises()
    const requestCountBeforeSearch = fetchMock.mock.calls.length

    const input = wrapper.find('input')
    await input.setValue('平安')
    const searchButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('搜索'))
    if (!searchButton) {
      throw new Error('expected search button')
    }
    await searchButton.trigger('click')
    await flushPromises()

    const searchRequest = fetchMock.mock.calls[requestCountBeforeSearch] as [string, RequestInit]
    expect(searchRequest[0]).toContain('/api/stocks?keyword=%E5%B9%B3%E5%AE%89&page=1&page_size=20')
  })

  it('backfills missing card quote from latest daily endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '000001.SZ',
            symbol: '000001',
            name: '平安银行',
            fullname: '平安银行股份有限公司',
            exchange: 'SZSE',
            close: null,
            pct_chg: null,
            trade_date: null,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            ts_code: '000001.SZ',
            trade_date: '2026-03-06',
            open: 11.0,
            high: 11.5,
            low: 10.9,
            close: 11.23,
            pre_close: 11.1,
            change: 0.13,
            pct_chg: 1.17,
            vol: 123000,
            amount: 321000,
            turnover_rate: null,
            volume_ratio: null,
            pe: null,
            pb: null,
            total_mv: null,
            circ_mv: null,
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountHomeView()
    await flushPromises()

    expect(wrapper.text()).toContain('11.23')
    expect(wrapper.text()).toContain('2026-03-06')

    const quoteCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(quoteCall[0]).toContain('/api/stocks/000001.SZ/daily?')
    expect(quoteCall[0]).toContain('limit=1')
    expect(quoteCall[0]).toContain('period=daily')
  })
})
