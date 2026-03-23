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

    expect(wrapper.text()).toContain('AI STOCK LAB')
    expect(wrapper.text()).toContain('by DreamBo')
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
})
