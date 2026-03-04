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
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          jsonResponse({
            instrument: {
              ts_code: '600000.SH',
              symbol: '600000',
              name: '浦发银行',
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
              turnover_rate: 1.8,
              volume_ratio: 1.1,
              pe: 5.8,
              pb: 0.62,
              total_mv: 2000000,
              circ_mv: 1800000,
            },
          ]),
        ),
    )

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
    expect(wrapper.text()).toContain('600000.SH')
    expect(wrapper.text()).toContain('8.25')
    expect(wrapper.text()).toContain('2026-03-03')
  })
})
