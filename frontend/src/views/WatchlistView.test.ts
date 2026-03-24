import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { MotionPlugin } from '@vueuse/motion'

vi.mock('element-plus/theme-chalk/base.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-button.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-card.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-empty.css', () => ({}))

import WatchlistView from './WatchlistView.vue'
import { i18n, setAppLocale } from '../i18n'
import { watchlistApi } from '../api/watchlist'
import { useAuthStore } from '../stores/auth'

const ElButtonStub = {
  name: 'ElButton',
  props: {
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    plain: { type: Boolean, default: false },
    type: { type: String, default: '' },
  },
  emits: ['click'],
  template: `
    <button
      class="el-button"
      :class="{
        'is-loading': loading,
        'is-disabled': disabled,
        'is-plain': plain,
        'el-button--primary': type === 'primary'
      }"
      :disabled="disabled"
      @click="$emit('click')"
    >
      <slot />
    </button>
  `,
}

const ElCardStub = {
  name: 'ElCard',
  template: '<article class="el-card"><slot /></article>',
}

const ElEmptyStub = {
  name: 'ElEmpty',
  props: {
    description: { type: String, default: '' },
  },
  template: '<div class="el-empty">{{ description }}</div>',
}

const elementPlusStubs = {
  ElButton: ElButtonStub,
  ElCard: ElCardStub,
  ElEmpty: ElEmptyStub,
}

const sampleWatchlistItems = [
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
]

describe('WatchlistView', () => {
  it('mounts without token and refreshes after token is set', async () => {
    setAppLocale('zh-CN')
    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.accessToken = ''
    authStore.user = null
    authStore.initialized = true

    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({
      items: sampleWatchlistItems,
    })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/watchlist', component: WatchlistView }],
    })
    await router.push('/watchlist')
    await router.isReady()

    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [pinia, router, i18n, MotionPlugin],
        components: elementPlusStubs,
      },
    })

    await flushPromises()

    expect(watchlistApi.getWatchlist).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('贵州茅台')

    authStore.accessToken = 'token'
    authStore.user = {
      id: 'user-1',
      username: 'watcher',
      email: 'watcher@example.com',
      is_active: true,
      user_level: 'user',
    }
    await flushPromises()

    expect(watchlistApi.getWatchlist).toHaveBeenCalledWith('token')
    expect(wrapper.text()).toContain('贵州茅台')
  })

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
      items: sampleWatchlistItems,
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
        plugins: [pinia, router, i18n, MotionPlugin],
        components: elementPlusStubs,
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
      items: sampleWatchlistItems,
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
        plugins: [pinia, router, i18n, MotionPlugin],
        components: elementPlusStubs,
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
    expect(wrapper.text()).toContain('自动分析联网增强：ON')
  })

  it('clears list immediately when token becomes empty after loaded', async () => {
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
      items: sampleWatchlistItems,
    })

    let resolveUpdate: ((value: Awaited<ReturnType<typeof watchlistApi.updateWatchlistItem>>) => void) | undefined
    vi.spyOn(watchlistApi, 'updateWatchlistItem').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpdate = resolve
        }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/watchlist', component: WatchlistView }],
    })
    await router.push('/watchlist')
    await router.isReady()

    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [pinia, router, i18n, MotionPlugin],
        components: elementPlusStubs,
      },
    })

    await flushPromises()
    expect(wrapper.text()).toContain('贵州茅台')

    const webSearchSwitch = wrapper.get('[data-testid="watchlist-web-search-600519.SH"]')
    await webSearchSwitch.trigger('click')
    await flushPromises()
    expect(webSearchSwitch.attributes('disabled')).toBeDefined()

    authStore.accessToken = ''
    authStore.user = null
    await flushPromises()

    expect(wrapper.text()).not.toContain('贵州茅台')
    expect(wrapper.find('[data-testid="watchlist-web-search-600519.SH"]').exists()).toBe(false)
    expect(wrapper.find('.el-button.is-loading').exists()).toBe(false)

    resolveUpdate?.({
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
  })
})
