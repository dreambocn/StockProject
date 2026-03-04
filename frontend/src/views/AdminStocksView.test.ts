import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import { i18n, setAppLocale } from '../i18n'
import { useAuthStore } from '../stores/auth'
import AdminStocksView from './AdminStocksView.vue'

const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

const mountAdminStocksView = async () => {
  setAppLocale('zh-CN')
  const pinia = createPinia()
  const authStore = useAuthStore(pinia)
  authStore.accessToken = 'admin-access-token'

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/admin/stocks', component: AdminStocksView }],
  })
  await router.push('/admin/stocks')
  await router.isReady()

  return mount(AdminStocksView, {
    global: {
      plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
    },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AdminStocksView', () => {
  it('renders paged stock records from admin database endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          items: [
            {
              ts_code: '000001.SZ',
              symbol: '000001',
              name: '平安银行',
              area: '深圳',
              industry: '银行',
              fullname: null,
              enname: null,
              cnspell: null,
              market: '主板',
              exchange: 'SZSE',
              curr_type: 'CNY',
              list_status: 'L',
              list_date: '1991-04-03',
              delist_date: null,
              is_hs: 'S',
              act_name: null,
              act_ent_type: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      ),
    )

    const wrapper = await mountAdminStocksView()
    await flushPromises()

    expect(wrapper.text()).toContain('股票管理中心')
    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('000001.SZ')
  })

  it('syncs stocks then reloads paged results when fetch button clicked', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          message: 'stock basic sync completed',
          total: 1,
          created: 1,
          updated: 0,
          list_statuses: ['G'],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountAdminStocksView()
    await flushPromises()

    const preListingButton = wrapper.get('[data-testid="preset-g"]')
    await preListingButton.trigger('click')

    const fetchButton = wrapper.get('[data-testid="fetch-with-params"]')
    await fetchButton.trigger('click')
    await flushPromises()

    const syncCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(syncCall[0]).toContain('/api/admin/stocks/full?list_status=G')
    expect(syncCall[1].method).toBe('POST')

    const queryCall = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(queryCall[0]).toContain('/api/admin/stocks?list_status=G&page=1&page_size=20')
    expect(queryCall[1].method).toBe('GET')
  })

  it('queries trade calendar from db-first stock endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            exchange: 'SSE',
            cal_date: '2026-03-03',
            is_open: '1',
            pretrade_date: '2026-03-02',
          },
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountAdminStocksView()
    await flushPromises()

    await wrapper.get('[data-testid="trade-cal-query"]').trigger('click')
    await flushPromises()

    const tradeCalCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(tradeCalCall[0]).toContain('/api/stocks/trade-cal?exchange=SSE')
    expect(tradeCalCall[1].method).toBe('GET')
    expect(wrapper.text()).toContain('2026-03-03')
    expect(wrapper.find('[data-testid="trade-cal-pagination"]').exists()).toBe(true)
  })
})
