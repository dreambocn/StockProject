import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import App from './App.vue'
import { setAppLocale } from './i18n'
import { i18n } from './i18n'
import HomeView from './views/HomeView.vue'
import AdminConsoleView from './views/AdminConsoleView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('App', () => {
  it('renders refreshed brand and stock dashboard title', async () => {
    setAppLocale('zh-CN')

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            ts_code: '000001.SZ',
            symbol: '000001',
            name: '平安银行',
            exchange: 'SZSE',
            close: 11.1,
            pct_chg: 1.37,
            trade_date: '2026-03-03',
          },
        ],
      }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/analysis', component: HomeView },
        { path: '/watchlist', component: HomeView },
        { path: '/profile', component: HomeView },
        { path: '/login', component: HomeView },
        { path: '/stocks/:tsCode', component: HomeView },
        { path: '/policy/documents', component: HomeView },
        { path: '/news/hot', component: HomeView },
      ],
    })
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    expect(wrapper.text()).toContain('PULSE STRATEGY')
    expect(wrapper.text()).toContain('脉策')
    expect(wrapper.text()).toContain('股票仪表盘')
    expect(wrapper.text()).toContain('中文')
    expect(wrapper.text()).toContain('EN')
    expect(wrapper.text()).toContain('分析')
    expect(wrapper.text()).toContain('关注')
  })

  it('moves locale slider when switching language', async () => {
    setAppLocale('zh-CN')

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            ts_code: '000001.SZ',
            symbol: '000001',
            name: '平安银行',
            exchange: 'SZSE',
            close: 11.1,
            pct_chg: 1.37,
            trade_date: '2026-03-03',
          },
        ],
      }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/analysis', component: HomeView },
        { path: '/watchlist', component: HomeView },
        { path: '/profile', component: HomeView },
        { path: '/login', component: HomeView },
        { path: '/stocks/:tsCode', component: HomeView },
        { path: '/policy/documents', component: HomeView },
        { path: '/news/hot', component: HomeView },
      ],
    })
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    const slider = wrapper.get('[data-testid="locale-slider"]')
    expect(slider.attributes('style')).toContain('translateX(0%)')

    const enButton = wrapper
      .findAll('button.locale-chip')
      .find((buttonWrapper) => buttonWrapper.text() === 'EN')
    expect(enButton).toBeDefined()
    await enButton!.trigger('click')

    expect(slider.attributes('style')).toContain('translateX(100%)')
  })

  it('shows admin nav entry for admin user', async () => {
    setAppLocale('zh-CN')
    localStorage.setItem('auth.accessToken', 'access-admin')
    localStorage.setItem('auth.refreshToken', 'refresh-admin')

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input) => {
        const url = String(input)
        if (url.includes('/api/auth/me')) {
          return {
            ok: true,
            json: async () => ({
              id: 'admin-1',
              username: 'root',
              email: 'root@example.com',
              is_active: true,
              user_level: 'admin',
            }),
          }
        }

        return {
          ok: true,
          json: async () => [
            {
              ts_code: '000001.SZ',
              symbol: '000001',
              name: '平安银行',
              exchange: 'SZSE',
              close: 11.1,
              pct_chg: 1.37,
              trade_date: '2026-03-03',
            },
          ],
        }
      }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/analysis', component: HomeView },
        { path: '/watchlist', component: HomeView },
        { path: '/profile', component: HomeView },
        { path: '/login', component: HomeView },
        { path: '/admin', component: AdminConsoleView },
        { path: '/admin/users', component: HomeView },
        { path: '/admin/stocks', component: HomeView },
        { path: '/stocks/:tsCode', component: HomeView },
        { path: '/policy/documents', component: HomeView },
        { path: '/news/hot', component: HomeView },
      ],
    })
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('后台管理')
    expect(wrapper.text()).not.toContain('股票管理')
  })

  it('keeps current stock context when opening analysis from the top nav', async () => {
    setAppLocale('zh-CN')

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/analysis', component: HomeView },
        { path: '/watchlist', component: HomeView },
        { path: '/profile', component: HomeView },
        { path: '/login', component: HomeView },
        { path: '/stocks/:tsCode', component: HomeView },
        { path: '/policy/documents', component: HomeView },
        { path: '/news/hot', component: HomeView },
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

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    const analysisLink = wrapper
      .findAll('a')
      .find((item) => item.text().includes('分析'))
    expect(analysisLink).toBeDefined()

    await analysisLink!.trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(router.currentRoute.value.path).toBe('/analysis')
    expect(router.currentRoute.value.query.ts_code).toBe('600000.SH')
    expect(router.currentRoute.value.query.source).toBe('hot_news')
    expect(router.currentRoute.value.query.topic).toBe('commodity_supply')
    expect(router.currentRoute.value.query.event_id).toBe('evt-hot-1')
    expect(router.currentRoute.value.query.event_title).toBe('国际油价高位震荡')
  })

  it('reuses the last focused analysis context from the top nav', async () => {
    setAppLocale('zh-CN')

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/analysis', component: HomeView },
        { path: '/watchlist', component: HomeView },
        { path: '/profile', component: HomeView },
        { path: '/login', component: HomeView },
        { path: '/stocks/:tsCode', component: HomeView },
        { path: '/policy/documents', component: HomeView },
        { path: '/news/hot', component: HomeView },
      ],
    })
    await router.push({
      path: '/analysis',
      query: {
        ts_code: '600519.SH',
        source: 'watchlist',
      },
    })
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await router.push('/')
    await router.isReady()

    const analysisLink = wrapper
      .findAll('a')
      .find((item) => item.text().includes('分析'))
    expect(analysisLink).toBeDefined()

    await analysisLink!.trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(router.currentRoute.value.path).toBe('/analysis')
    expect(router.currentRoute.value.query.ts_code).toBe('600519.SH')
    expect(router.currentRoute.value.query.source).toBe('watchlist')
  })
})
