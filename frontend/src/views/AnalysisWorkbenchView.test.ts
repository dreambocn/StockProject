import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import AnalysisWorkbenchView from './AnalysisWorkbenchView.vue'
import { i18n, setAppLocale } from '../i18n'
import { analysisApi, type StockAnalysisSummaryResponse } from '../api/analysis'

const createRouterWithQuery = () =>
  createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/analysis', component: AnalysisWorkbenchView }],
  })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AnalysisWorkbenchView', () => {
  it('shows empty state without ts_code and avoids API call', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({ path: '/analysis' })
    await router.isReady()

    const spy = vi.spyOn(analysisApi, 'getStockAnalysisSummary')
    const wrapper = mount(AnalysisWorkbenchView, {
      global: { plugins: [router, i18n, ElementPlus, MotionPlugin] },
    })

    await flushPromises()

    expect(spy).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请输入 TS Code')
  })

  it('renders pending fallback when report is missing', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({ path: '/analysis', query: { ts_code: '600519.SH' } })
    await router.isReady()

    const summary: StockAnalysisSummaryResponse = {
      ts_code: '600519.SH',
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
      latest_snapshot: null,
      status: 'partial',
      generated_at: '2026-03-23T00:00:00Z',
      topic: null,
      published_from: null,
      published_to: null,
      event_count: 0,
      events: [],
      report: null,
    }

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue(summary)

    const wrapper = mount(AnalysisWorkbenchView, {
      global: { plugins: [router, i18n, ElementPlus, MotionPlugin] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('分析正在生成')
  })

  it('shows summary details when report is ready', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({ path: '/analysis', query: { ts_code: '600519.SH' } })
    await router.isReady()

    const summary: StockAnalysisSummaryResponse = {
      ts_code: '600519.SH',
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
      latest_snapshot: null,
      status: 'ready',
      generated_at: '2026-03-23T00:00:00Z',
      topic: null,
      published_from: null,
      published_to: null,
      event_count: 1,
      events: [
        {
          event_id: 'evt-1',
          scope: 'hot',
          title: '政策推动',
          published_at: '2026-03-01T00:00:00Z',
          source: 'eastmoney_global',
          macro_topic: 'regulation_policy',
          event_type: 'policy',
          event_tags: ['政策'],
          sentiment_label: 'positive',
          sentiment_score: 0.5,
          anchor_trade_date: '2026-03-02',
          window_return_pct: 2.1,
          window_volatility: 1.2,
          abnormal_volume_ratio: 1.4,
          correlation_score: 0.8,
          confidence: 'high',
          link_status: 'linked',
        },
      ],
      report: {
        status: 'ready',
        summary: '因政策推动...',
        risk_points: ['政策波动风险'],
        factor_breakdown: [
          {
            factor_key: 'policy',
            factor_label: '政策',
            weight: 0.5,
            direction: 'positive',
            evidence: ['政策出台'],
            reason: '政策利好',
          },
        ],
        generated_at: '2026-03-23T01:00:00Z',
      },
    }

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue(summary)

    const wrapper = mount(AnalysisWorkbenchView, {
      global: { plugins: [router, i18n, ElementPlus, MotionPlugin] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('因政策推动...')
    expect(wrapper.text()).toContain('政策')
    expect(wrapper.text()).toContain('政策波动风险')
  })

  it('keeps report summary visible when status is partial', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH', topic: 'regulation_policy', source: 'hot_news' },
    })
    await router.isReady()

    const summary: StockAnalysisSummaryResponse = {
      ts_code: '600519.SH',
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
      latest_snapshot: null,
      status: 'partial',
      generated_at: '2026-03-23T00:00:00Z',
      topic: 'regulation_policy',
      published_from: null,
      published_to: null,
      event_count: 1,
      events: [],
      report: {
        status: 'partial',
        summary: '由于大模型暂不可用，当前返回规则摘要。',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-03-23T01:00:00Z',
      },
    }

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue(summary)

    const wrapper = mount(AnalysisWorkbenchView, {
      global: { plugins: [router, i18n, ElementPlus, MotionPlugin] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('由于大模型暂不可用')
    expect(wrapper.text()).toContain('hot_news')
    expect(wrapper.text()).toContain('regulation_policy')
  })
})
