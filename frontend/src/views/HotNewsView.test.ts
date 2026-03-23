import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import HotNewsView from './HotNewsView.vue'
import { i18n, setAppLocale } from '../i18n'

const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

describe('HotNewsView', () => {
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
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse([
          {
            topic: 'commodity_supply',
            affected_assets: ['原油'],
            beneficiary_sectors: ['油气开采'],
            pressure_sectors: ['航空运输'],
            a_share_targets: ['中国海油'],
            a_share_candidates: [
              {
                ts_code: '600938.SH',
                symbol: '600938',
                name: '中国海油',
                industry: '石油开采',
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
        { path: '/analysis', component: { template: '<div>analysis</div>' } },
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
      .find((item) => item.text().includes('研判此股'))
    expect(actionButton).toBeDefined()

    await actionButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/analysis')
    expect(router.currentRoute.value.query.ts_code).toBe('600938.SH')
    expect(router.currentRoute.value.query.source).toBe('hot_news')
    expect(router.currentRoute.value.query.topic).toBe('commodity_supply')
  })
})
