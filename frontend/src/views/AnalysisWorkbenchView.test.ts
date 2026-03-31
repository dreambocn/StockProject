import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { MotionPlugin } from '@vueuse/motion'

vi.mock('element-plus/theme-chalk/base.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-button.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-card.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-skeleton.css', () => ({}))
vi.mock('element-plus/theme-chalk/el-switch.css', () => ({}))

import AnalysisWorkbenchView from './AnalysisWorkbenchView.vue'
import { i18n, setAppLocale } from '../i18n'
import { analysisApi, type StockAnalysisSummaryResponse } from '../api/analysis'
import { watchlistApi } from '../api/watchlist'
import { useAuthStore } from '../stores/auth'

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

const ElCardStub = {
  name: 'ElCard',
  template: '<div class="el-card"><slot /></div>',
}

const ElSkeletonStub = {
  name: 'ElSkeleton',
  template: '<div class="el-skeleton" />',
}

const ElButtonStub = {
  name: 'ElButton',
  props: {
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    plain: { type: Boolean, default: false },
  },
  emits: ['click'],
  template: `
    <button
      class="el-button"
      :class="{
        'is-plain': plain,
        'is-disabled': disabled,
        'is-loading': loading
      }"
      :disabled="disabled"
      @click="$emit('click')"
    >
      <slot />
    </button>
  `,
}

const ElSwitchStub = {
  name: 'ElSwitch',
  props: {
    modelValue: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  methods: {
    handleChange(
      this: { $emit: (event: 'update:modelValue', value: boolean) => void },
      event: Event,
    ) {
      const target = event.target as HTMLInputElement | null
      this.$emit('update:modelValue', Boolean(target?.checked))
    },
  },
  template: `
    <label class="el-switch">
      <input
        type="checkbox"
        :checked="modelValue"
        @change="handleChange"
      />
    </label>
  `,
}

const elementPlusStubs = {
  ElCard: ElCardStub,
  ElSkeleton: ElSkeletonStub,
  ElButton: ElButtonStub,
  ElSwitch: ElSwitchStub,
}

const mountWorkbench = async (router: ReturnType<typeof createRouter>) => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore()
  authStore.initialized = true

  const wrapper = mount(AnalysisWorkbenchView, {
    global: {
      plugins: [pinia, router, i18n, MotionPlugin],
      components: elementPlusStubs,
    },
  })

  await flushPromises()
  return { wrapper }
}

const createDeferred = <T>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve
  })
  return { promise, resolve }
}

const createMinimalSummary = (tsCode: string, reportSummary: string): StockAnalysisSummaryResponse => ({
  ts_code: tsCode,
  instrument: {
    ts_code: tsCode,
    symbol: tsCode.split('.')[0] ?? tsCode,
    name: `${tsCode} 标的`,
    area: '',
    industry: '行业',
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
  generated_at: '2026-03-23T08:00:00Z',
  topic: null,
  published_from: null,
  published_to: null,
  event_count: 0,
  events: [],
  report: {
    id: `report-${tsCode}`,
    status: 'ready',
    summary: reportSummary,
    risk_points: [],
    factor_breakdown: [],
    generated_at: '2026-03-23T08:10:00Z',
    trigger_source: 'manual',
    used_web_search: false,
    web_search_status: 'disabled',
    content_format: 'markdown',
  },
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
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })
    const { wrapper } = await mountWorkbench(router)

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
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [summary.report!],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

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
    expect(router.currentRoute.value.query.event_id).toBe('evt-policy')
    expect(router.currentRoute.value.query.event_title).toBe('监管政策优化白酒消费环境')
  })

  it('passes event context to api and pins anchor event to top', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: {
        ts_code: '600519.SH',
        topic: 'commodity_supply',
        event_id: 'evt-anchor',
        event_title: '国际油价高位震荡',
        source: 'hot_news',
      },
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
      status: 'ready',
      generated_at: '2026-03-23T08:00:00Z',
      topic: 'commodity_supply',
      event_context_status: 'direct',
      event_context_message: null,
      published_from: null,
      published_to: null,
      event_count: 2,
      events: [
        {
          event_id: 'evt-other',
          scope: 'hot',
          title: '其他事件',
          published_at: '2026-03-23T09:00:00Z',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
          event_type: 'news',
          event_tags: ['新闻'],
          sentiment_label: 'neutral',
          sentiment_score: 0.1,
          anchor_trade_date: null,
          window_return_pct: 4.2,
          window_volatility: 1.1,
          abnormal_volume_ratio: 1.2,
          correlation_score: 0.95,
          confidence: 'high',
          link_status: 'linked',
        },
        {
          event_id: 'evt-anchor',
          scope: 'hot',
          title: '国际油价高位震荡',
          published_at: '2026-03-22T09:00:00Z',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
          event_type: 'news',
          event_tags: ['原油'],
          sentiment_label: 'positive',
          sentiment_score: 0.8,
          anchor_trade_date: null,
          window_return_pct: 1.1,
          window_volatility: 0.8,
          abnormal_volume_ratio: 1.1,
          correlation_score: 0.62,
          confidence: 'medium',
          link_status: 'linked',
        },
      ],
      report: {
        status: 'ready',
        summary: '锚点事件带来结构化影响。',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-03-23T08:10:00Z',
        anchor_event_id: 'evt-anchor',
        anchor_event_title: '国际油价高位震荡',
        structured_sources: [{ provider: 'akshare', count: 1 }],
      },
    }

    const summarySpy = vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue(summary)
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [summary.report!],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

    expect(summarySpy).toHaveBeenCalledWith('600519.SH', {
      topic: 'commodity_supply',
      eventId: 'evt-anchor',
    })
    expect(wrapper.text()).toContain('国际油价高位震荡')
    const eventTitles = wrapper.findAll('[data-testid="analysis-event-title"]').map((item) => item.text())
    expect(eventTitles[0]).toBe('国际油价高位震荡')
  })

  it('renders hero actions as a split toolbar with grouped controls', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: {
        ts_code: '600519.SH',
        topic: 'regulation_policy',
        source: 'hot_news',
        event_id: 'evt-policy',
        event_title: '监管政策优化白酒消费环境',
      },
    })
    await router.isReady()

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue({
      ts_code: '600519.SH',
      instrument: null,
      latest_snapshot: null,
      status: 'ready',
      generated_at: '2026-03-23T08:00:00Z',
      topic: 'regulation_policy',
      published_from: null,
      published_to: null,
      event_count: 0,
      events: [],
      report: {
        id: 'report-toolbar',
        status: 'ready',
        summary: '## 快报摘要',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-03-23T08:10:00Z',
        trigger_source: 'manual',
        used_web_search: false,
        web_search_status: 'disabled',
        content_format: 'markdown',
      },
    } as StockAnalysisSummaryResponse)
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

    const toolbar = wrapper.get('[data-testid="analysis-hero-toolbar"]')
    expect(toolbar.find('[data-testid="analysis-hero-controls"]').exists()).toBe(true)
    expect(toolbar.find('[data-testid="analysis-hero-action-cluster"]').exists()).toBe(true)
    expect(toolbar.find('[data-testid="analysis-hero-action-rail"]').exists()).toBe(true)
    expect(toolbar.find('[data-testid="analysis-hero-primary-actions"]').exists()).toBe(true)
    expect(toolbar.find('[data-testid="analysis-hero-secondary-actions"]').exists()).toBe(true)
    expect(toolbar.find('[data-testid="analysis-switch-label"]').exists()).toBe(true)
    expect(toolbar.find('[data-testid="analysis-switch-toggle"]').exists()).toBe(true)
    expect(toolbar.find('[data-testid="analysis-hero-action-cluster"]').classes()).toContain(
      'analysis-hero__action-cluster',
    )
    expect(toolbar.find('[data-testid="analysis-source-action"]').classes()).toContain('is-plain')
    expect(toolbar.find('[data-testid="analysis-source-action"]').classes()).not.toContain('is-text')
    expect(toolbar.findAll('.analysis-action-btn--outline')).toHaveLength(5)

    const orderedButtons = toolbar
      .findAll('button')
      .map((item) => item.text().trim())
      .filter(Boolean)
    expect(orderedButtons).toEqual([
      '刷新分析',
      '查看个股详情',
      '导出 Markdown',
      '导出 HTML',
      expect.stringContaining('关注'),
      '返回热点主题',
    ])

    const stockDetailButton = toolbar
      .findAll('button')
      .find((item) => item.text().includes('查看个股详情'))
    expect(stockDetailButton).toBeDefined()
    await stockDetailButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/stocks/600519.SH')
    expect(router.currentRoute.value.query.source).toBe('hot_news')
    expect(router.currentRoute.value.query.topic).toBe('regulation_policy')
    expect(router.currentRoute.value.query.event_id).toBe('evt-policy')
    expect(router.currentRoute.value.query.event_title).toBe('监管政策优化白酒消费环境')
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
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    const createSessionSpy = vi.spyOn(analysisApi, 'createAnalysisSession').mockResolvedValue({
      session_id: null,
      report_id: null,
      status: 'completed',
      reused: false,
      cached: true,
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

    expect(wrapper.text()).toContain('分析正在生成')
    expect(wrapper.text()).toContain('刷新分析')
    expect(wrapper.text()).toContain('返回个股详情')

    const refreshButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('刷新分析'))
    expect(refreshButton).toBeDefined()
    await refreshButton!.trigger('click')
    await flushPromises()

    expect(createSessionSpy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledTimes(2)

    const detailButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('返回个股详情'))
    expect(detailButton).toBeDefined()
    await detailButton!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/stocks/600519.SH')
  })

  it('renders markdown summary and report archive entries', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH' },
    })
    await router.isReady()

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue({
      ts_code: '600519.SH',
      instrument: null,
      latest_snapshot: null,
      status: 'ready',
      generated_at: '2026-03-23T08:00:00Z',
      topic: null,
      published_from: null,
      published_to: null,
      event_count: 0,
      events: [],
      report: {
        id: 'report-current',
        status: 'ready',
        summary: '# 一级标题\n\n- 条目一',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-03-23T08:00:00Z',
        trigger_source: 'manual',
        used_web_search: false,
        web_search_status: 'disabled',
        content_format: 'markdown',
      },
    } as StockAnalysisSummaryResponse)
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [
        {
          id: 'report-current',
          status: 'ready',
          summary: '# 一级标题\n\n- 条目一',
          risk_points: [],
          factor_breakdown: [],
          generated_at: '2026-03-23T08:00:00Z',
          trigger_source: 'manual',
          used_web_search: false,
          web_search_status: 'disabled',
          content_format: 'markdown',
        },
      ],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

    const markdownBody = wrapper.get('[data-testid="analysis-markdown"]')
    expect(markdownBody.html()).toContain('<h1')
    expect(wrapper.text()).toContain('历史报告')
    expect(wrapper.text()).toContain('手动触发')
  })

  it('renders structured web citations separately from markdown body', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH', event_id: 'evt-anchor', event_title: '国际油价高位震荡' },
    })
    await router.isReady()

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue({
      ts_code: '600519.SH',
      instrument: null,
      latest_snapshot: null,
      status: 'ready',
      generated_at: '2026-03-23T08:00:00Z',
      topic: 'commodity_supply',
      event_context_status: 'direct',
      event_context_message: null,
      published_from: null,
      published_to: null,
      event_count: 1,
      events: [
        {
          event_id: 'evt-anchor',
          scope: 'hot',
          title: '国际油价高位震荡',
          published_at: '2026-03-23T08:00:00Z',
          source: 'eastmoney_global',
          macro_topic: 'commodity_supply',
          event_type: 'news',
          event_tags: ['原油'],
          sentiment_label: 'positive',
          sentiment_score: 0.7,
          anchor_trade_date: null,
          window_return_pct: 1.2,
          window_volatility: 0.8,
          abnormal_volume_ratio: 1.1,
          correlation_score: 0.85,
          confidence: 'high',
          link_status: 'linked',
        },
      ],
      report: {
        id: 'report-web',
        status: 'ready',
        summary: '## 核心判断\n\n原油事件带动风险偏好修复。',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-03-23T08:10:00Z',
        trigger_source: 'manual',
        used_web_search: true,
        web_search_status: 'used',
        content_format: 'markdown',
        structured_sources: [{ provider: 'akshare', count: 1 }],
        web_sources: [
          {
            title: '国际油价收涨',
            url: 'https://finance.example.com/oil',
            source: 'Reuters',
            published_at: '2026-03-23T08:05:00Z',
            snippet: '市场继续关注供给端扰动。',
            domain: 'finance.example.com',
            metadata_status: 'enriched',
          },
          {
            title: '补充链接',
            url: 'https://unknown.example.com/report',
            source: 'unknown.example.com',
            published_at: null,
            snippet: null,
            domain: 'unknown.example.com',
            metadata_status: 'domain_inferred',
          },
        ],
      },
    } as StockAnalysisSummaryResponse)
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

    expect(wrapper.text()).toContain('国际油价收涨')
    expect(wrapper.text()).toContain('Reuters')
    expect(wrapper.text()).toContain('市场继续关注供给端扰动')
    expect(wrapper.text()).toContain('finance.example.com')
    expect(wrapper.text()).toContain('补充链接')
    expect(wrapper.text()).toContain('unknown.example.com')
    expect(wrapper.text()).toContain('时间待补全')
    expect(wrapper.get('[data-testid="analysis-markdown"]').html()).toContain('核心判断')
    const citationLink = wrapper.find('a[href="https://finance.example.com/oil"]')
    expect(citationLink.exists()).toBe(true)
  })

  it('creates analysis session and applies streaming delta content', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH' },
    })
    await router.isReady()

    vi.spyOn(analysisApi, 'getStockAnalysisSummary')
      .mockResolvedValueOnce({
        ts_code: '600519.SH',
        instrument: null,
        latest_snapshot: null,
        status: 'pending',
        generated_at: null,
        topic: null,
        published_from: null,
        published_to: null,
        event_count: 0,
        events: [],
        report: null,
      })
      .mockResolvedValueOnce({
        ts_code: '600519.SH',
        instrument: null,
        latest_snapshot: null,
        status: 'ready',
        generated_at: '2026-03-23T08:10:00Z',
        topic: null,
        published_from: null,
        published_to: null,
        event_count: 0,
        events: [],
        report: {
          id: 'report-latest',
          status: 'ready',
          summary: '## 实时更新\n\n- 第一条',
          risk_points: [],
          factor_breakdown: [],
          generated_at: '2026-03-23T08:10:00Z',
          trigger_source: 'manual',
          used_web_search: false,
          web_search_status: 'disabled',
          content_format: 'markdown',
        },
      } as StockAnalysisSummaryResponse)

    vi.spyOn(analysisApi, 'getStockAnalysisReports')
      .mockResolvedValueOnce({ ts_code: '600519.SH', items: [] })
      .mockResolvedValueOnce({
        ts_code: '600519.SH',
        items: [
          {
            id: 'report-latest',
            status: 'ready',
            summary: '## 实时更新\n\n- 第一条',
            risk_points: [],
            factor_breakdown: [],
            generated_at: '2026-03-23T08:10:00Z',
            trigger_source: 'manual',
            used_web_search: false,
            web_search_status: 'disabled',
            content_format: 'markdown',
          },
        ],
      })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    vi.spyOn(analysisApi, 'createAnalysisSession').mockResolvedValue({
      session_id: 'session-1',
      report_id: null,
      status: 'queued',
      reused: false,
      cached: false,
    })
    const openSpy = vi
      .spyOn(analysisApi, 'openAnalysisSessionEvents')
      .mockImplementation((_sessionId, handlers) => {
        handlers.onStatus?.({ session_id: 'session-1', status: 'running' })
        handlers.onDelta?.({
          session_id: 'session-1',
          delta: '## 实时更新\n\n- 第一条',
          content: '## 实时更新\n\n- 第一条',
        })
        handlers.onCompleted?.({
          session_id: 'session-1',
          report_id: 'report-latest',
          status: 'ready',
        })
        return () => undefined
      })

    const { wrapper } = await mountWorkbench(router)

    const refreshButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('刷新分析'))
    expect(refreshButton).toBeDefined()
    await refreshButton!.trigger('click')
    await flushPromises()

    expect(openSpy).toHaveBeenCalled()
    expect(wrapper.text()).toContain('实时更新')
    expect(wrapper.text()).toContain('第一条')
  })

  it('stops active stream and clears streaming markdown before loading next ts_code', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH', topic: 'old-topic', event_id: 'evt-old' },
    })
    await router.isReady()

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockImplementation(async (nextTsCode) => {
      if (nextTsCode === '600519.SH') {
        return {
          ts_code: '600519.SH',
          instrument: null,
          latest_snapshot: null,
          status: 'pending',
          generated_at: null,
          topic: 'old-topic',
          published_from: null,
          published_to: null,
          event_count: 0,
          events: [],
          report: null,
        } as StockAnalysisSummaryResponse
      }
      return createMinimalSummary(nextTsCode, '## 新股票报告')
    })
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })
    vi.spyOn(analysisApi, 'createAnalysisSession').mockResolvedValue({
      session_id: 'session-still-streaming',
      report_id: null,
      status: 'queued',
      reused: false,
      cached: false,
    })

    const stopStreamingSpy = vi.fn()
    vi.spyOn(analysisApi, 'openAnalysisSessionEvents').mockImplementation((_sessionId, handlers) => {
      handlers.onDelta?.({
        session_id: 'session-still-streaming',
        delta: '## 旧流式内容',
        content: '## 旧流式内容',
      })
      return stopStreamingSpy
    })

    const { wrapper } = await mountWorkbench(router)

    const refreshButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('刷新分析'))
    expect(refreshButton).toBeDefined()
    await refreshButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('旧流式内容')

    await router.push({
      path: '/analysis',
      query: { ts_code: '000001.SZ', topic: 'new-topic', event_id: 'evt-new' },
    })
    await flushPromises()

    expect(stopStreamingSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('旧流式内容')
    expect(wrapper.text()).toContain('新股票报告')
  })

  it('inherits watchlist web-search default but only applies it to the current manual session', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH' },
    })
    await router.isReady()

    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.initialized = true
    authStore.accessToken = 'token'

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue({
      ts_code: '600519.SH',
      instrument: null,
      latest_snapshot: null,
      status: 'ready',
      generated_at: '2026-03-23T08:00:00Z',
      topic: null,
      published_from: null,
      published_to: null,
      event_count: 0,
      events: [],
      report: {
        id: 'report-current',
        status: 'ready',
        summary: '## 摘要',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-03-23T08:00:00Z',
        trigger_source: 'manual',
        used_web_search: true,
        web_search_status: 'used',
        content_format: 'markdown',
      },
    } as StockAnalysisSummaryResponse)
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({
      items: [
        {
          id: 'watch-1',
          ts_code: '600519.SH',
          hourly_sync_enabled: true,
          daily_analysis_enabled: true,
          web_search_enabled: true,
          last_hourly_sync_at: null,
          last_daily_analysis_at: null,
          created_at: '2026-03-23T08:00:00Z',
          updated_at: '2026-03-23T08:00:00Z',
          instrument: null,
          latest_report: null,
        },
      ],
    })
    const createSessionSpy = vi.spyOn(analysisApi, 'createAnalysisSession').mockResolvedValue({
      session_id: null,
      report_id: 'report-current',
      status: 'completed',
      reused: false,
      cached: true,
    })

    const wrapper = mount(AnalysisWorkbenchView, {
      global: {
        plugins: [pinia, router, i18n, MotionPlugin],
        components: elementPlusStubs,
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('本次分析联网增强')
    expect(wrapper.text()).toContain('已继承关注设置，可仅对本次分析临时调整。')
    expect(wrapper.text()).toContain('已启用联网增强')

    const webSearchSwitch = wrapper.findComponent({ name: 'ElSwitch' })
    expect(webSearchSwitch.exists()).toBe(true)
    expect((webSearchSwitch.props() as { modelValue?: boolean }).modelValue).toBe(true)

    const refreshButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('刷新分析'))
    expect(refreshButton).toBeDefined()
    await refreshButton!.trigger('click')
    await flushPromises()

    expect(createSessionSpy).toHaveBeenCalledWith(
      '600519.SH',
      expect.objectContaining({
        use_web_search: true,
        trigger_source: 'manual',
      }),
    )
  })

  it('reloads watchlist when token is restored and keeps manual switch state after token clears', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH' },
    })
    await router.isReady()

    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.initialized = true
    authStore.accessToken = ''

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue(
      createMinimalSummary('600519.SH', '## 初始报告'),
    )
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    const watchlistSpy = vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({
      items: [
        {
          id: 'watch-token-change',
          ts_code: '600519.SH',
          hourly_sync_enabled: true,
          daily_analysis_enabled: true,
          web_search_enabled: true,
          last_hourly_sync_at: null,
          last_daily_analysis_at: null,
          created_at: '2026-03-23T08:00:00Z',
          updated_at: '2026-03-23T08:00:00Z',
          instrument: null,
          latest_report: null,
        },
      ],
    })

    const wrapper = mount(AnalysisWorkbenchView, {
      global: {
        plugins: [pinia, router, i18n, MotionPlugin],
        components: elementPlusStubs,
      },
    })
    await flushPromises()

    expect(watchlistSpy).not.toHaveBeenCalled()

    authStore.accessToken = 'new-token'
    await flushPromises()

    expect(watchlistSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('已继承关注设置，可仅对本次分析临时调整。')
    expect(wrapper.text()).toContain('已启用联网增强')

    const webSearchSwitch = wrapper.findComponent({ name: 'ElSwitch' })
    expect(webSearchSwitch.exists()).toBe(true)
    expect((webSearchSwitch.props() as { modelValue?: boolean }).modelValue).toBe(true)

    await webSearchSwitch.vm.$emit('update:modelValue', false)
    await flushPromises()
    expect((wrapper.findComponent({ name: 'ElSwitch' }).props() as { modelValue?: boolean }).modelValue).toBe(
      false,
    )

    authStore.accessToken = ''
    await flushPromises()

    expect(wrapper.text()).toContain('登录后关注')
    expect(wrapper.text()).not.toContain('已继承关注设置，可仅对本次分析临时调整。')
    expect((wrapper.findComponent({ name: 'ElSwitch' }).props() as { modelValue?: boolean }).modelValue).toBe(
      false,
    )
  })

  it('ignores stale workbench responses when ts_code changes rapidly', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH', topic: 'old-topic' },
    })
    await router.isReady()

    const oldSummaryDeferred = createDeferred<StockAnalysisSummaryResponse>()
    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockImplementation((nextTsCode) => {
      if (nextTsCode === '600519.SH') {
        return oldSummaryDeferred.promise
      }
      return Promise.resolve(createMinimalSummary(nextTsCode, '## 新请求摘要'))
    })
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

    await router.push({
      path: '/analysis',
      query: { ts_code: '000001.SZ', topic: 'new-topic' },
    })
    await flushPromises()

    expect(wrapper.get('.analysis-hero__code').text()).toContain('000001.SZ')

    oldSummaryDeferred.resolve(createMinimalSummary('600519.SH', '## 旧请求摘要'))
    await flushPromises()

    expect(wrapper.get('.analysis-hero__code').text()).toContain('000001.SZ')
    expect(wrapper.get('.analysis-hero__title').text()).toContain('000001.SZ 标的')
    expect(wrapper.get('[data-testid="analysis-markdown"]').text()).toContain('新请求摘要')
  })

  it('renders enriched web sources from history reports when summary report is missing', async () => {
    setAppLocale('zh-CN')
    const router = createRouterWithQuery()
    await router.push({
      path: '/analysis',
      query: { ts_code: '600519.SH', source: 'stock_detail' },
    })
    await router.isReady()

    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue({
      ts_code: '600519.SH',
      instrument: null,
      latest_snapshot: null,
      status: 'partial',
      generated_at: '2026-03-23T08:00:00Z',
      topic: null,
      published_from: null,
      published_to: null,
      event_count: 0,
      events: [],
      report: null,
    } as StockAnalysisSummaryResponse)
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [
        {
          id: 'report-history-1',
          status: 'ready',
          summary: '## 历史报告\n\n补全后的引用已可直接展示。',
          risk_points: [],
          factor_breakdown: [],
          generated_at: '2026-03-23T08:10:00Z',
          trigger_source: 'manual',
          used_web_search: true,
          web_search_status: 'used',
          content_format: 'markdown',
          web_sources: [
            {
              title: '国际油价收涨',
              url: 'https://finance.example.com/oil',
              source: 'Reuters',
              published_at: '2026-03-23T08:05:00Z',
              snippet: '市场继续关注供给端扰动。',
              domain: 'finance.example.com',
              metadata_status: 'enriched',
            },
          ],
        },
      ],
    })
    vi.spyOn(watchlistApi, 'getWatchlist').mockResolvedValue({ items: [] })

    const { wrapper } = await mountWorkbench(router)

    expect(wrapper.text()).toContain('国际油价收涨')
    expect(wrapper.text()).toContain('Reuters')
    expect(wrapper.text()).toContain('finance.example.com')
    expect(wrapper.text()).toContain('市场继续关注供给端扰动。')
  })
})
