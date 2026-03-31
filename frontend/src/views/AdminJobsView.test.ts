import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import AdminJobsView from './AdminJobsView.vue'
import { i18n, setAppLocale } from '../i18n'
import { useAuthStore } from '../stores/auth'

const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AdminJobsView', () => {
  it('loads summary, list and detail', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          total: 2,
          status_counts: { running: 1, failed: 1 },
          type_counts: { analysis_generate: 1, news_fetch: 1 },
          recent_failures: [{ id: 'job-2', job_type: 'news_fetch' }],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              id: 'job-1',
              job_type: 'analysis_generate',
              status: 'running',
              trigger_source: 'manual',
              resource_type: 'stock',
              resource_key: '600519.SH',
              summary: '执行中',
              linked_entity: { entity_type: 'analysis_generation_session', entity_id: 'session-1' },
              started_at: '2026-03-31T10:00:00Z',
              heartbeat_at: '2026-03-31T10:01:00Z',
              finished_at: null,
              duration_ms: null,
              created_at: '2026-03-31T10:00:00Z',
              updated_at: '2026-03-31T10:01:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'job-1',
          job_type: 'analysis_generate',
          status: 'running',
          trigger_source: 'manual',
          resource_type: 'stock',
          resource_key: '600519.SH',
          summary: '执行中',
          linked_entity: { entity_type: 'analysis_generation_session', entity_id: 'session-1' },
          started_at: '2026-03-31T10:00:00Z',
          heartbeat_at: '2026-03-31T10:01:00Z',
          finished_at: null,
          duration_ms: null,
          created_at: '2026-03-31T10:00:00Z',
          updated_at: '2026-03-31T10:01:00Z',
          idempotency_key: 'idem-1',
          payload_json: { ts_code: '600519.SH' },
          metrics_json: { event_count: 3 },
          error_type: null,
          error_message: null,
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.accessToken = 'admin-token'
    authStore.user = {
      id: 'admin-1',
      username: 'admin',
      email: 'admin@example.com',
      is_active: true,
      user_level: 'admin',
    }
    authStore.initialized = true

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/admin/jobs', component: AdminJobsView }],
    })
    await router.push('/admin/jobs')
    await router.isReady()

    const wrapper = mount(AdminJobsView, {
      global: {
        plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('后台任务中心')
    expect(wrapper.text()).toContain('总任务数')
    expect(wrapper.text()).toContain('analysis_generate')

    await wrapper.get('.job-row').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('任务详情')
    expect(wrapper.text()).toContain('analysis_generation_session')
    expect(wrapper.text()).toContain('"event_count": 3')
  })
})
