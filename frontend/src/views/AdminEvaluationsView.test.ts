import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import { i18n, setAppLocale } from '../i18n'
import { useAuthStore } from '../stores/auth'
import AdminEvaluationsView from './AdminEvaluationsView.vue'


const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

const catalogPayload = {
  datasets: [
    {
      id: 'dataset-1',
      dataset_key: 'analysis_eval_dataset_v1',
      label: '人工标注样本集 v1',
      description: '用于答辩展示',
      sample_count: 3,
      date_from: '2026-01-01',
      date_to: '2026-03-24',
    },
  ],
  experiment_groups: [
    {
      dataset_key: 'analysis_eval_dataset_v1',
      experiment_group_key: 'prompt_profile_compare_v1',
      latest_baseline_run: {
        id: 'baseline-1',
        run_key: 'run-baseline-1',
        experiment_group_key: 'prompt_profile_compare_v1',
        variant_key: 'baseline',
        variant_label: '基线方案',
        prompt_profile_key: 'production_current',
        model_name: 'gpt-5.1-codex-mini',
        sample_count: 3,
        event_top1_hit_rate: 0.33,
        factor_top1_accuracy: 0.67,
        citation_metadata_completeness_rate: 0.33,
        avg_latency_ms: 1800,
        created_at: '2026-03-24T09:00:00Z',
      },
      latest_candidate_run: {
        id: 'optimized-1',
        run_key: 'run-optimized-1',
        experiment_group_key: 'prompt_profile_compare_v1',
        variant_key: 'optimized',
        variant_label: '优化方案',
        prompt_profile_key: 'evidence_first_v2',
        model_name: 'gpt-5.1-codex-mini',
        sample_count: 3,
        event_top1_hit_rate: 0.67,
        factor_top1_accuracy: 0.67,
        citation_metadata_completeness_rate: 0.67,
        avg_latency_ms: 1500,
        created_at: '2026-03-24T09:05:00Z',
      },
      baseline_runs: [
        {
          id: 'baseline-1',
          run_key: 'run-baseline-1',
          experiment_group_key: 'prompt_profile_compare_v1',
          variant_key: 'baseline',
          variant_label: '基线方案',
          prompt_profile_key: 'production_current',
          model_name: 'gpt-5.1-codex-mini',
          sample_count: 3,
          event_top1_hit_rate: 0.33,
          factor_top1_accuracy: 0.67,
          citation_metadata_completeness_rate: 0.33,
          avg_latency_ms: 1800,
          created_at: '2026-03-24T09:00:00Z',
        },
      ],
      candidate_runs: [
        {
          id: 'optimized-1',
          run_key: 'run-optimized-1',
          experiment_group_key: 'prompt_profile_compare_v1',
          variant_key: 'optimized',
          variant_label: '优化方案',
          prompt_profile_key: 'evidence_first_v2',
          model_name: 'gpt-5.1-codex-mini',
          sample_count: 3,
          event_top1_hit_rate: 0.67,
          factor_top1_accuracy: 0.67,
          citation_metadata_completeness_rate: 0.67,
          avg_latency_ms: 1500,
          created_at: '2026-03-24T09:05:00Z',
        },
      ],
    },
  ],
}

const primaryGroup = catalogPayload.experiment_groups[0]!
const baselineRun = primaryGroup.latest_baseline_run!
const candidateRun = primaryGroup.latest_candidate_run!

const overviewPayload = {
  empty: false,
  dataset: catalogPayload.datasets[0],
  experiment_group_key: 'prompt_profile_compare_v1',
  baseline_run: baselineRun,
  candidate_run: candidateRun,
  metric_cards: {
    event_top1_hit_rate: {
      metric_key: 'event_top1_hit_rate',
      label: '事件关联命中率',
      unit: 'rate',
      baseline_value: 0.33,
      candidate_value: 0.67,
    },
    factor_top1_accuracy: {
      metric_key: 'factor_top1_accuracy',
      label: 'Top1 因子命中率',
      unit: 'rate',
      baseline_value: 0.67,
      candidate_value: 0.67,
    },
    citation_metadata_completeness_rate: {
      metric_key: 'citation_metadata_completeness_rate',
      label: '引用元数据完整率',
      unit: 'rate',
      baseline_value: 0.33,
      candidate_value: 0.67,
    },
    avg_latency_ms: {
      metric_key: 'avg_latency_ms',
      label: '平均分析耗时',
      unit: 'ms',
      baseline_value: 1800,
      candidate_value: 1500,
    },
  },
  bar_chart: {
    categories: ['事件关联命中率', 'Top1 因子命中率', '引用元数据完整率', '平均分析耗时'],
    baseline_series: [0.33, 0.67, 0.33, 1800],
    candidate_series: [0.67, 0.67, 0.67, 1500],
  },
  distribution_chart: {
    improved: 1,
    unchanged: 1,
    regressed: 1,
  },
  top_improved_cases: [
    {
      case_key: 'case-improved',
      ts_code: '600519.SH',
      topic: 'monetary_policy',
      anchor_event_title: '消费支持政策持续加码',
      expected_top_factor_key: 'policy',
      notes: '显著改善',
      baseline_score: 0,
      candidate_score: 1,
      score_delta: 1,
      classification: 'improved',
      baseline_top_event_title: '其他事件',
      candidate_top_event_title: '消费支持政策持续加码',
      baseline_top_factor_key: 'news',
      candidate_top_factor_key: 'policy',
      baseline_citation_metadata_completeness_rate: 0,
      candidate_citation_metadata_completeness_rate: 1,
      baseline_latency_ms: 1800,
      candidate_latency_ms: 1500,
    },
  ],
  top_regressed_cases: [
    {
      case_key: 'case-regressed',
      ts_code: '000001.SZ',
      topic: 'regulation_policy',
      anchor_event_title: '银行监管边际收紧',
      expected_top_factor_key: 'policy',
      notes: '明显退化',
      baseline_score: 1,
      candidate_score: 0,
      score_delta: -1,
      classification: 'regressed',
      baseline_top_event_title: '银行监管边际收紧',
      candidate_top_event_title: '其他事件',
      baseline_top_factor_key: 'policy',
      candidate_top_factor_key: 'news',
      baseline_citation_metadata_completeness_rate: 1,
      candidate_citation_metadata_completeness_rate: 0,
      baseline_latency_ms: 1700,
      candidate_latency_ms: 1500,
    },
  ],
  recent_cases: [
    {
      case_key: 'case-improved',
      ts_code: '600519.SH',
      topic: 'monetary_policy',
      anchor_event_title: '消费支持政策持续加码',
      expected_top_factor_key: 'policy',
      notes: '显著改善',
      baseline_score: 0,
      candidate_score: 1,
      score_delta: 1,
      classification: 'improved',
      baseline_top_event_title: '其他事件',
      candidate_top_event_title: '消费支持政策持续加码',
      baseline_top_factor_key: 'news',
      candidate_top_factor_key: 'policy',
      baseline_citation_metadata_completeness_rate: 0,
      candidate_citation_metadata_completeness_rate: 1,
      baseline_latency_ms: 1800,
      candidate_latency_ms: 1500,
    },
  ],
}

const caseDetailPayload = {
  case: {
    case_key: 'case-improved',
    ts_code: '600519.SH',
    topic: 'monetary_policy',
    anchor_event_title: '消费支持政策持续加码',
    expected_top_factor_key: 'policy',
    notes: '显著改善',
  },
  baseline_run: baselineRun,
  candidate_run: candidateRun,
  baseline_result: {
    event_top1_hit: false,
    factor_top1_hit: false,
    citation_metadata_completeness_rate: 0,
    latency_ms: 1800,
    top_event_title: '其他事件',
    top_factor_key: 'news',
    web_source_count: 0,
    result_snapshot: {
      summary: '基线摘要',
    },
    case_score: 0,
    classification: 'improved',
  },
  candidate_result: {
    event_top1_hit: true,
    factor_top1_hit: true,
    citation_metadata_completeness_rate: 1,
    latency_ms: 1500,
    top_event_title: '消费支持政策持续加码',
    top_factor_key: 'policy',
    web_source_count: 2,
    result_snapshot: {
      summary: '优化摘要',
    },
    case_score: 1,
    classification: 'improved',
  },
}

const mountAdminEvaluationsView = async () => {
  setAppLocale('zh-CN')
  const pinia = createPinia()
  const authStore = useAuthStore(pinia)
  authStore.accessToken = 'admin-access-token'
  authStore.user = {
    id: 'admin-1',
    username: 'root',
    email: 'root@example.com',
    is_active: true,
    user_level: 'admin',
  }

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/admin/evaluations', component: AdminEvaluationsView }],
  })
  await router.push('/admin/evaluations')
  await router.isReady()

  return mount(AdminEvaluationsView, {
    attachTo: document.body,
    global: {
      plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
    },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('AdminEvaluationsView', () => {
  it('renders overview cards and chart containers', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(catalogPayload))
        .mockResolvedValueOnce(jsonResponse(overviewPayload)),
    )

    const wrapper = await mountAdminEvaluationsView()
    await flushPromises()

    expect(wrapper.text()).toContain('实验结果中心')
    expect(wrapper.text()).toContain('事件关联命中率')
    expect(wrapper.text()).toContain('平均分析耗时')
    expect(wrapper.find('[data-testid="evaluation-bar-chart"]').exists()).toBe(true)
    expect(
      wrapper.find('[data-testid="evaluation-distribution-chart"]').exists(),
    ).toBe(true)
  })

  it('opens case detail drawer when clicking a case row', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(catalogPayload))
        .mockResolvedValueOnce(jsonResponse(overviewPayload))
        .mockResolvedValueOnce(jsonResponse(caseDetailPayload)),
    )

    const wrapper = await mountAdminEvaluationsView()
    await flushPromises()

    await wrapper.get('[data-testid="case-row-case-improved"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('消费支持政策持续加码')
    expect(wrapper.text()).toContain('基线摘要')
    expect(wrapper.text()).toContain('优化摘要')
  })

  it('shows cli empty state when no runs exist', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(catalogPayload))
        .mockResolvedValueOnce(
          jsonResponse({
            ...overviewPayload,
            empty: true,
            baseline_run: null,
            candidate_run: null,
            metric_cards: {},
            bar_chart: {
              categories: [],
              baseline_series: [],
              candidate_series: [],
            },
            distribution_chart: {
              improved: 0,
              unchanged: 0,
              regressed: 0,
            },
            top_improved_cases: [],
            top_regressed_cases: [],
            recent_cases: [],
          }),
        ),
    )

    const wrapper = await mountAdminEvaluationsView()
    await flushPromises()

    expect(wrapper.text()).toContain('导入样本集命令')
    expect(wrapper.text()).toContain('执行实验命令')
    expect(wrapper.text()).toContain('import_analysis_evaluation_dataset.py')
    expect(wrapper.text()).toContain('run_analysis_evaluation.py')
  })
})
