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
          { symbol: 'AAPL', name: 'Apple', price: 213.48, change: 1.42 },
        ],
      }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/profile', component: HomeView },
        { path: '/login', component: HomeView },
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
  })

  it('moves locale slider when switching language', async () => {
    setAppLocale('zh-CN')

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          { symbol: 'AAPL', name: 'Apple', price: 213.48, change: 1.42 },
        ],
      }),
    )

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/profile', component: HomeView },
        { path: '/login', component: HomeView },
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
})
