import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import WatchlistView from './WatchlistView.vue'
import { i18n, setAppLocale } from '../i18n'
import { watchlistApi } from '../api/watchlist'
import { useAuthStore } from '../stores/auth'


describe('WatchlistView', () => {
  it('loads watchlist and navigates to analysis page', async () => {
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

    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({
      items: [
        {
          id: 'item-1',
          ts_code: '600519.SH',
          hourly_sync_enabled: true,
          daily_analysis_enabled: true,
          web_search_enabled: false,
          last_hourly_sync_at: '2026-03-23T08:05:00Z',
          last_daily_analysis_at: '2026-03-23T18:10:00Z',
          created_at: '2026-03-23T07:00:00Z',
          updated_at: '2026-03-23T18:10:00Z',
          instrument: {
            ts_code: '600519.SH',
            symbol: '600519',
            name: '贵州茅台',
            area: '',
            industry: '白酒',
            fullname: '',
            enname: null,
            cnspell: null,
            market: '主板',
            exchange: 'SSE',
            curr_type: '',
            list_status: 'L',
            list_date: null,
            delist_date: null,
            is_hs: 'N',
            act_name: null,
            act_ent_type: null,
          },
          latest_report: null,
        },
      ],
    })
    vi.spyOn(watchlistApi, 'getWatchlistFeed').mockResolvedValue({
      items: [
        {
          ts_code: '600519.SH',
          instrument: null,
          latest_report: null,
          last_hourly_sync_at: '2026-03-23T08:05:00Z',
          last_daily_analysis_at: '2026-03-23T18:10:00Z',
        },
      ],
    })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/watchlist', component: WatchlistView },
        { path: '/analysis', component: { template: '<div>analysis</div>' } },
      ],
    })
    await router.push('/watchlist')
    await router.isReady()

    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('我的关注')
    expect(wrapper.text()).toContain('贵州茅台')

    const actionButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('进入分析'))
    expect(actionButton).toBeDefined()

    await actionButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/analysis')
    expect(router.currentRoute.value.query.ts_code).toBe('600519.SH')
  })

  it('updates watchlist automation switches in place', async () => {
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

    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({
      items: [
        {
          id: 'item-1',
          ts_code: '600519.SH',
          hourly_sync_enabled: true,
          daily_analysis_enabled: true,
          web_search_enabled: false,
          last_hourly_sync_at: '2026-03-23T08:05:00Z',
          last_daily_analysis_at: '2026-03-23T18:10:00Z',
          created_at: '2026-03-23T07:00:00Z',
          updated_at: '2026-03-23T18:10:00Z',
          instrument: {
            ts_code: '600519.SH',
            symbol: '600519',
            name: '贵州茅台',
            area: '',
            industry: '白酒',
            fullname: '',
            enname: null,
            cnspell: null,
            market: '主板',
            exchange: 'SSE',
            curr_type: '',
            list_status: 'L',
            list_date: null,
            delist_date: null,
            is_hs: 'N',
            act_name: null,
            act_ent_type: null,
          },
          latest_report: null,
        },
      ],
    })
    vi.spyOn(watchlistApi, 'updateWatchlistItem').mockResolvedValue({
      id: 'item-1',
      ts_code: '600519.SH',
      hourly_sync_enabled: true,
      daily_analysis_enabled: true,
      web_search_enabled: true,
      last_hourly_sync_at: '2026-03-23T08:05:00Z',
      last_daily_analysis_at: '2026-03-23T18:10:00Z',
      created_at: '2026-03-23T07:00:00Z',
      updated_at: '2026-03-23T18:12:00Z',
      instrument: null,
      latest_report: null,
    })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/watchlist', component: WatchlistView }],
    })
    await router.push('/watchlist')
    await router.isReady()

    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const webSearchSwitch = wrapper.get('[data-testid="watchlist-web-search-600519.SH"]')
    await webSearchSwitch.trigger('click')
    await flushPromises()

    expect(watchlistApi.updateWatchlistItem).toHaveBeenCalledWith(
      'token',
      '600519.SH',
      { web_search_enabled: true },
    )
    expect(wrapper.text()).toContain('联网增强：ON')
  })
})
