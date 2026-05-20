import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import AdminEvaluationsView from './AdminEvaluationsView.vue'
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

const runSummary = {
  total_cases: 10,
  profiles: ['production_current', 'evidence_first_v2'],
  metric_breakdown: {
    production_current: {
      citation_completeness: 0.65,
      evidence_coverage: 0.7,
      risk_notice_coverage: 0.6,
      conclusion_stability: 0.72,
      failure_rate: 0,
    },
    evidence_first_v2: {
      citation_completeness: 0.95,
      evidence_coverage: 1,
      risk_notice_coverage: 0.9,
      conclusion_stability: 0.88,
      failure_rate: 0,
    },
  },
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AdminEvaluationsView', () => {
  it('loads datasets, runs evaluation, filters and opens run detail', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse([
          {
            dataset: 'default_research_cases',
            title: '默认研究评估集',
            case_count: 10,
            event_types: ['政策驱动', '公告驱动'],
            topics: ['政策支持新型储能'],
            case_tags: ['政策', '证据优先'],
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: 'eval-1',
          dataset: 'default_research_cases',
          profiles: ['production_current', 'evidence_first_v2'],
          status: 'success',
          started_at: '2026-05-20T10:00:00Z',
          completed_at: '2026-05-20T10:00:01Z',
          summary: runSummary,
          case_results: [
            {
              case_id: 'policy-energy-storage-001',
              dataset: 'default_research_cases',
              ts_code: '300750.SZ',
              topic: '政策支持新型储能',
              event_type: '政策驱动',
              case_tags: ['政策', '证据优先'],
              prompt_profile: 'evidence_first_v2',
              conclusion: '证据优先结论',
              citations: ['policy-energy-storage-001:政策原文'],
              evidence_kinds: ['政策原文', '结构化事件'],
              risk_notices: ['补贴退坡'],
              metric_breakdown: runSummary.metric_breakdown.evidence_first_v2,
              failure_reason: null,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            run_id: 'eval-1',
            dataset: 'default_research_cases',
            profiles: ['production_current', 'evidence_first_v2'],
            status: 'success',
            started_at: '2026-05-20T10:00:00Z',
            completed_at: '2026-05-20T10:00:01Z',
            summary: runSummary,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse([
          {
            run_id: 'eval-1',
            dataset: 'default_research_cases',
            profiles: ['production_current', 'evidence_first_v2'],
            status: 'success',
            started_at: '2026-05-20T10:00:00Z',
            completed_at: '2026-05-20T10:00:01Z',
            summary: runSummary,
          },
        ]),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: 'eval-1',
          dataset: 'default_research_cases',
          profiles: ['production_current', 'evidence_first_v2'],
          status: 'success',
          started_at: '2026-05-20T10:00:00Z',
          completed_at: '2026-05-20T10:00:01Z',
          summary: runSummary,
          case_results: [
            {
              case_id: 'policy-energy-storage-001',
              dataset: 'default_research_cases',
              ts_code: '300750.SZ',
              topic: '政策支持新型储能',
              event_type: '政策驱动',
              case_tags: ['政策', '证据优先'],
              prompt_profile: 'evidence_first_v2',
              conclusion: '证据优先结论',
              citations: ['policy-energy-storage-001:政策原文'],
              evidence_kinds: ['政策原文', '结构化事件'],
              risk_notices: ['补贴退坡'],
              metric_breakdown: runSummary.metric_breakdown.evidence_first_v2,
              failure_reason: null,
            },
          ],
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
      routes: [{ path: '/admin/evaluations', component: AdminEvaluationsView }],
    })
    await router.push('/admin/evaluations')
    await router.isReady()

    const wrapper = mount(AdminEvaluationsView, {
      global: {
        plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('研究评估中心')
    expect(wrapper.text()).toContain('默认研究评估集')

    await wrapper.get('[data-testid="evaluation-run"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('引用完整率')
    expect(wrapper.text()).toContain('证据覆盖率')
    expect(wrapper.text()).toContain('evidence_first_v2')

    await wrapper.get('[data-testid="evaluation-filter-profile"]').setValue('evidence_first_v2')
    await wrapper.get('[data-testid="evaluation-filter-event-type"]').setValue('政策驱动')
    await wrapper.get('[data-testid="evaluation-filter-topic"]').setValue('政策')
    await wrapper.get('[data-testid="evaluation-apply-filters"]').trigger('click')
    await flushPromises()

    const filteredCall = fetchMock.mock.calls[4] as [string, RequestInit]
    expect(filteredCall[0]).toContain('prompt_profile=evidence_first_v2')

    await wrapper.get('[data-testid="evaluation-run-row"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('policy-energy-storage-001')
    expect(wrapper.text()).toContain('补贴退坡')
  })
})
