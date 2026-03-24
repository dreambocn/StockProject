import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import HotNewsView from './HotNewsView.vue'
import { i18n, setAppLocale } from '../i18n'

const HOT_NEWS_ANCHOR_STORAGE_KEY = 'hot-news-anchor-event-selections'

const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

describe('HotNewsView', () => {
  it('persists selected anchor event across remounts', async () => {
    window.localStorage.clear()

    const payloads = [
      jsonResponse([
        {
          event_id: 'evt-hot-1',
          cluster_key: 'cluster-1',
          providers: ['akshare'],
          source_coverage: 'AK',
          title: '国际油价高位震荡',
          summary: '原油供需偏紧',
          published_at: '2026-03-03T09:00:00',
          url: 'https://finance.example.com/a/1',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
        },
        {
          event_id: 'evt-hot-2',
          cluster_key: 'cluster-2',
          providers: ['akshare'],
          source_coverage: 'AK',
          title: 'OPEC 会议释放减产信号',
          summary: '供给端预期继续收紧',
          published_at: '2026-03-03T10:00:00',
          url: 'https://finance.example.com/a/2',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
        },
      ]),
      jsonResponse([
        {
          topic: 'commodity_supply',
          affected_assets: ['原油'],
          beneficiary_sectors: ['油气开采'],
          pressure_sectors: ['航空运输'],
          a_share_targets: ['中国海油'],
          anchor_event: {
            event_id: 'evt-hot-1',
            title: '国际油价高位震荡',
            published_at: '2026-03-03T09:00:00',
            providers: ['akshare'],
            source_coverage: 'AK',
          },
          a_share_candidates: [
            {
              ts_code: '600938.SH',
              symbol: '600938',
              name: '中国海油',
              industry: '石油开采',
              relevance_score: 45,
              match_reasons: ['命中主题目标股'],
              evidence_summary: '命中主题目标股',
              source_hit_count: 1,
            },
          ],
        },
      ]),
    ]

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(payloads[0])
      .mockResolvedValueOnce(payloads[1])
      .mockResolvedValueOnce(payloads[0])
      .mockResolvedValueOnce(payloads[1])
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/news/hot', component: HotNewsView },
        { path: '/stocks/:tsCode', component: { template: '<div>stock</div>' } },
      ],
    })
    await router.push('/news/hot')
    await router.isReady()

    const firstWrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const switchButton = firstWrapper
      .findAll('button')
      .find((item) => item.text().includes('OPEC 会议释放减产信号'))
    expect(switchButton).toBeDefined()
    await switchButton!.trigger('click')
    await flushPromises()

    expect(window.localStorage.getItem(HOT_NEWS_ANCHOR_STORAGE_KEY)).toContain('evt-hot-2')
    firstWrapper.unmount()

    const secondWrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })
    await flushPromises()

    const detailButton = secondWrapper
      .findAll('button')
      .find((item) => item.text().includes('查看详情'))
    expect(detailButton).toBeDefined()
    await detailButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.event_id).toBe('evt-hot-2')
    expect(router.currentRoute.value.query.event_title).toBe('OPEC 会议释放减产信号')
  })

  it('loads and renders hot news list', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse([
          {
            title: '中东局势升级',
            summary: '避险情绪升温',
            published_at: '2026-03-03T09:00:00',
            url: 'https://finance.example.com/a/2',
            source: 'eastmoney_global',
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/news/hot', component: HotNewsView }],
    })
    await router.push('/news/hot')
    await router.isReady()

    const wrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('热点新闻')
    expect(wrapper.text()).toContain('中东局势升级')
    expect(wrapper.text()).toContain('避险情绪升温')

    const firstCall = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(firstCall[0]).toContain('/api/news/hot')
  })

  it('reads topic from route query and requests filtered hot news on first load', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse([
          {
            title: '中东局势升级',
            summary: '避险情绪升温',
            published_at: '2026-03-03T09:00:00',
            url: 'https://finance.example.com/a/2',
            source: 'eastmoney_global',
            macro_topic: 'geopolitical_conflict',
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            topic: 'geopolitical_conflict',
            affected_assets: ['原油', '黄金'],
            beneficiary_sectors: ['油气开采', '黄金采选'],
            pressure_sectors: ['航空运输'],
            a_share_targets: ['中国海油', '山东黄金'],
            a_share_candidates: [],
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/news/hot', component: HotNewsView }],
    })
    await router.push({ path: '/news/hot', query: { topic: 'geopolitical_conflict' } })
    await router.isReady()

    const wrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('地缘冲突')
    const initialHotNewsCall = fetchMock.mock.calls[0] as [string, RequestInit]
    const initialImpactCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(initialHotNewsCall[0]).toContain('topic=geopolitical_conflict')
    expect(initialImpactCall[0]).toContain('topic=geopolitical_conflict')
  })

  it('navigates to analysis workbench from a-share candidate entry', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([
        {
          event_id: 'evt-hot-1',
          cluster_key: 'cluster-1',
          providers: ['akshare'],
          source_coverage: 'AK',
          title: '国际油价高位震荡',
          summary: '原油供需偏紧',
          published_at: '2026-03-03T09:00:00',
          url: 'https://finance.example.com/a/1',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
        },
      ]))
      .mockResolvedValueOnce(
        jsonResponse([
          {
            topic: 'commodity_supply',
            affected_assets: ['原油'],
            beneficiary_sectors: ['油气开采'],
            pressure_sectors: ['航空运输'],
            a_share_targets: ['中国海油'],
            anchor_event: {
              event_id: 'evt-hot-1',
              title: '国际油价高位震荡',
              published_at: '2026-03-03T09:00:00',
              providers: ['akshare'],
              source_coverage: 'AK',
            },
            a_share_candidates: [
              {
                ts_code: '600938.SH',
                symbol: '600938',
                name: '中国海油',
                industry: '石油开采',
                relevance_score: 45,
                match_reasons: ['命中主题目标股'],
                evidence_summary: '命中主题目标股',
                source_hit_count: 1,
              },
            ],
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/news/hot', component: HotNewsView },
        { path: '/stocks/:tsCode', component: { template: '<div>stock</div>' } },
      ],
    })
    await router.push('/news/hot')
    await router.isReady()

    const wrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const actionButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('查看详情'))
    expect(actionButton).toBeDefined()

    await actionButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/stocks/600938.SH')
    expect(router.currentRoute.value.query.topic).toBe('commodity_supply')
    expect(router.currentRoute.value.query.source).toBe('hot_news')
    expect(router.currentRoute.value.query.event_id).toBe('evt-hot-1')
    expect(router.currentRoute.value.query.event_title).toBe('国际油价高位震荡')
  })

  it('renders anchor event and candidate scoring details', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([
        {
          event_id: 'evt-hot-1',
          cluster_key: 'cluster-1',
          providers: ['akshare'],
          source_coverage: 'AK',
          title: '国际油价高位震荡',
          summary: '原油供需偏紧',
          published_at: '2026-03-03T09:00:00',
          url: 'https://finance.example.com/a/1',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
        },
      ]))
      .mockResolvedValueOnce(
        jsonResponse([
          {
            topic: 'commodity_supply',
            affected_assets: ['原油'],
            beneficiary_sectors: ['油气开采'],
            pressure_sectors: ['航空运输'],
            a_share_targets: ['中国海油'],
            anchor_event: {
              event_id: 'evt-hot-1',
              title: '国际油价高位震荡',
              published_at: '2026-03-03T09:00:00',
              providers: ['akshare'],
              source_coverage: 'AK',
            },
            a_share_candidates: [
              {
                ts_code: '600938.SH',
                symbol: '600938',
                name: '中国海油',
                industry: '石油开采',
                relevance_score: 45,
                match_reasons: ['命中主题目标股', '命中行业关键词：石油'],
                evidence_summary: '命中主题目标股；命中行业关键词：石油',
                source_hit_count: 2,
              },
            ],
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/news/hot', component: HotNewsView },
        { path: '/stocks/:tsCode', component: { template: '<div>stock</div>' } },
      ],
    })
    await router.push('/news/hot')
    await router.isReady()

    const wrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('国际油价高位震荡')
    expect(wrapper.text()).toContain('AK')
    expect(wrapper.text()).toContain('45')
    expect(wrapper.text()).toContain('命中主题目标股')
    expect(wrapper.text()).toContain('命中行业关键词：石油')

    const detailButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('查看详情'))
    expect(detailButton).toBeDefined()

    await detailButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/stocks/600938.SH')
    expect(router.currentRoute.value.query.source).toBe('hot_news')
    expect(router.currentRoute.value.query.topic).toBe('commodity_supply')
  })

  it('renders candidate enhancement badges and evidence cards', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([
        {
          event_id: 'evt-hot-1',
          cluster_key: 'cluster-1',
          providers: ['akshare'],
          source_coverage: 'AK',
          title: '国际油价高位震荡',
          summary: '原油供需偏紧',
          published_at: '2026-03-03T09:00:00',
          url: 'https://finance.example.com/a/1',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
        },
      ]))
      .mockResolvedValueOnce(
        jsonResponse([
          {
            topic: 'commodity_supply',
            affected_assets: ['原油'],
            beneficiary_sectors: ['油气开采'],
            pressure_sectors: ['航空运输'],
            a_share_targets: ['中国海油'],
            anchor_event: {
              event_id: 'evt-hot-1',
              title: '国际油价高位震荡',
              published_at: '2026-03-03T09:00:00',
              providers: ['akshare'],
              source_coverage: 'AK',
            },
            a_share_candidates: [
              {
                ts_code: '600938.SH',
                symbol: '600938',
                name: '中国海油',
                industry: '石油开采',
                relevance_score: 55,
                match_reasons: ['命中主题目标股', '百度热搜命中 1 次', '近30日研报 2 篇'],
                evidence_summary: '命中主题目标股；百度热搜命中 1 次；近30日研报 2 篇',
                source_hit_count: 3,
                source_breakdown: [
                  { source: 'hot_search', count: 1 },
                  { source: 'research_report', count: 2 },
                ],
                freshness_score: 85,
                candidate_confidence: '高',
                evidence_items: [
                  {
                    ts_code: '600938.SH',
                    symbol: '600938',
                    name: '中国海油',
                    evidence_kind: 'hot_search',
                    title: '中国海油进入百度热搜',
                    summary: '百度热搜排名第 1 位',
                    published_at: '2026-03-23T08:00:00',
                    url: null,
                    source: 'baidu_hot_search',
                  },
                  {
                    ts_code: '600938.SH',
                    symbol: '600938',
                    name: '中国海油',
                    evidence_kind: 'research_report',
                    title: '油价上行驱动盈利改善',
                    summary: '机构发布研报',
                    published_at: '2026-03-22T08:00:00',
                    url: null,
                    source: 'eastmoney_research_report',
                  },
                ],
              },
            ],
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/news/hot', component: HotNewsView },
        { path: '/stocks/:tsCode', component: { template: '<div>stock</div>' } },
      ],
    })
    await router.push('/news/hot')
    await router.isReady()

    const wrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('石油开采')
    expect(wrapper.text()).toContain('高')
    expect(wrapper.text()).toContain('85')
    expect(wrapper.text()).toContain('热搜 1 / 研报 2')
    expect(wrapper.text()).toContain('中国海油进入百度热搜')
    expect(wrapper.text()).toContain('油价上行驱动盈利改善')
  })
})
