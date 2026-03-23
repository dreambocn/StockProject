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
    routes: [
      { path: '/', component: { template: '<div>home</div>' } },
      { path: '/news/hot', component: { template: '<div>hot</div>' } },
      { path: '/stocks/:tsCode', component: { template: '<div>stock detail</div>' } },
      { path: '/analysis', component: AnalysisWorkbenchView },
    ],
  })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AnalysisWorkbenchView', () => {
  it('shows empty state actions without ts_code and avoids API call', async () => {
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
    expect(wrapper.text()).toContain('去热点新闻')
    expect(wrapper.text()).toContain('返回首页')

    const hotNewsButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('去热点新闻'))
    expect(hotNewsButton).toBeDefined()
    await hotNewsButton!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/news/hot')
  })

  it('renders translated overview, factor ranking and event filters for professional analysis', async () => {
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
      latest_snapshot: {
        ts_code: '600519.SH',
        trade_date: '2026-03-23',
        open: 1680,
        high: 1695,
        low: 1672,
        close: 1688.88,
        pre_close: 1671.2,
        change: 17.68,
        pct_chg: 1.06,
        vol: 123456,
        amount: 654321,
        turnover_rate: null,
        volume_ratio: null,
        pe: null,
        pb: null,
        total_mv: null,
        circ_mv: null,
      },
      status: 'partial',
      generated_at: '2026-03-23T08:00:00Z',
      topic: 'regulation_policy',
      published_from: null,
      published_to: null,
      event_count: 3,
      events: [
        {
          event_id: 'evt-news',
          scope: 'hot',
          title: '行业景气延续',
          published_at: '2026-03-23T07:00:00Z',
          source: 'eastmoney_global',
          macro_topic: 'industry',
          event_type: 'news',
          event_tags: ['行业'],
          sentiment_label: 'neutral',
          sentiment_score: 0.1,
          anchor_trade_date: '2026-03-23',
          window_return_pct: 1.2,
          window_volatility: 0.8,
          abnormal_volume_ratio: 1.1,
          correlation_score: 0.62,
          confidence: 'medium',
          link_status: 'linked',
        },
        {
          event_id: 'evt-policy',
          scope: 'policy',
          title: '监管政策优化白酒消费环境',
          published_at: '2026-03-22T08:00:00Z',
          source: 'policy_feed',
          macro_topic: 'regulation_policy',
          event_type: 'policy',
          event_tags: ['政策', '监管'],
          sentiment_label: 'positive',
          sentiment_score: 0.8,
          anchor_trade_date: '2026-03-23',
          window_return_pct: 3.5,
          window_volatility: 1.2,
          abnormal_volume_ratio: 1.8,
          correlation_score: 0.93,
          confidence: 'high',
          link_status: 'linked',
        },
        {
          event_id: 'evt-announcement',
          scope: 'stock',
          title: '公司公告提示渠道调整',
          published_at: '2026-03-21T08:00:00Z',
          source: 'cninfo_announcement',
          macro_topic: 'announcement',
          event_type: 'announcement',
          event_tags: ['公告'],
          sentiment_label: 'negative',
          sentiment_score: -0.4,
          anchor_trade_date: null,
          window_return_pct: null,
          window_volatility: null,
          abnormal_volume_ratio: null,
          correlation_score: null,
          confidence: 'low',
          link_status: 'pending',
        },
      ],
      report: {
        status: 'partial',
        summary: '政策与行业景气共同支撑短线情绪，但公告分支仍需继续跟踪。',
        risk_points: ['公告信息尚未完成量化关联'],
        factor_breakdown: [
          {
            factor_key: 'sentiment',
            factor_label: '情绪',
            weight: 0.18,
            direction: 'neutral',
            evidence: ['市场分歧仍在'],
            reason: '短线情绪偏谨慎',
          },
          {
            factor_key: 'policy',
            factor_label: '政策',
            weight: 0.56,
            direction: 'positive',
            evidence: ['监管政策优化'],
            reason: '政策边际改善提升关注度',
          },
          {
            factor_key: 'announcement',
            factor_label: '公告',
            weight: 0.26,
            direction: 'negative',
            evidence: ['渠道调整公告'],
            reason: '仍有执行不确定性',
          },
        ],
        generated_at: '2026-03-23T08:10:00Z',
      },
    }

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue(summary)

    const wrapper = mount(AnalysisWorkbenchView, {
      global: { plugins: [router, i18n, ElementPlus, MotionPlugin] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('部分完成')
    expect(wrapper.text()).toContain('当前为降级或不完整分析')
    expect(wrapper.text()).toContain('最高权重因子')
    expect(wrapper.text()).toContain('政策')
    expect(wrapper.text()).toContain('56.0%')
    expect(wrapper.text()).toContain('利好')
    expect(wrapper.text()).toContain('高')
    expect(wrapper.text()).toContain('返回热点主题')

    const eventTitles = wrapper.findAll('[data-testid="analysis-event-title"]').map((item) => item.text())
    expect(eventTitles).toEqual([
      '监管政策优化白酒消费环境',
      '行业景气延续',
      '公司公告提示渠道调整',
    ])

    const policyFilter = wrapper
      .findAll('button')
      .find((item) => item.text().includes('政策'))
    expect(policyFilter).toBeDefined()
    await policyFilter!.trigger('click')
    await flushPromises()

    const filteredEventTitles = wrapper
      .findAll('[data-testid="analysis-event-title"]')
      .map((item) => item.text())
    expect(filteredEventTitles).toEqual(['监管政策优化白酒消费环境'])

    const backButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('返回热点主题'))
    expect(backButton).toBeDefined()
    await backButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/news/hot')
    expect(router.currentRoute.value.query.topic).toBe('regulation_policy')
  })

  it('shows pending workspace with refresh action when report is missing', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH', source: 'stock_detail' },
    })
    await router.isReady()

    const summary: StockAnalysisSummaryResponse = {
      ts_code: '600519.SH',
      instrument: null,
      latest_snapshot: null,
      status: 'pending',
      generated_at: '2026-03-23T00:00:00Z',
      topic: null,
      published_from: null,
      published_to: null,
      event_count: 0,
      events: [],
      report: null,
    }

    const spy = vi
      .spyOn(analysisApi, 'getStockAnalysisSummary')
      .mockResolvedValue(summary)

    const wrapper = mount(AnalysisWorkbenchView, {
      global: { plugins: [router, i18n, ElementPlus, MotionPlugin] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('分析正在生成')
    expect(wrapper.text()).toContain('刷新分析')
    expect(wrapper.text()).toContain('返回个股详情')

    const refreshButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('刷新分析'))
    expect(refreshButton).toBeDefined()
    await refreshButton!.trigger('click')
    await flushPromises()

    expect(spy).toHaveBeenCalledTimes(2)

    const detailButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('返回个股详情'))
    expect(detailButton).toBeDefined()
    await detailButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/stocks/600519.SH')
  })
})
