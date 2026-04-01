import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import AnalysisWorkbenchView from './AnalysisWorkbenchView.vue'
import { analysisApi } from '../api/analysis'
import { i18n, setAppLocale } from '../i18n'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AnalysisWorkbench export', () => {
  it('exports selected report as markdown', async () => {
    vi.spyOn(analysisApi, 'getStockAnalysisSummary').mockResolvedValue({
      ts_code: '600519.SH',
      instrument: { ts_code: '600519.SH', symbol: '600519', name: '贵州茅台', fullname: '贵州茅台酒股份有限公司', area: null, industry: '白酒', enname: null, cnspell: null, market: null, exchange: 'SSE', curr_type: null, list_status: 'L', list_date: null, delist_date: null, is_hs: null, act_name: null, act_ent_type: null },
      latest_snapshot: null,
      status: 'ready',
      generated_at: '2026-03-31T10:00:00Z',
      topic: null,
      published_from: null,
      published_to: null,
      event_count: 0,
      events: [],
      report: {
        id: 'report-1',
        status: 'ready',
        summary: '测试摘要',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-03-31T10:00:00Z',
        content_format: 'markdown',
      },
    } as never)
    vi.spyOn(analysisApi, 'getStockAnalysisReports').mockResolvedValue({
      ts_code: '600519.SH',
      items: [
        {
          id: 'report-1',
          status: 'ready',
          summary: '测试摘要',
          risk_points: [],
          factor_breakdown: [],
          generated_at: '2026-03-31T10:00:00Z',
          content_format: 'markdown',
        },
      ],
    } as never)
    vi.spyOn(analysisApi, 'exportReport').mockResolvedValue('# 测试导出')
    vi.useFakeTimers()
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    const removeSpy = vi.spyOn(document.body, 'removeChild')

    const clickSpy = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'a') {
        return {
          click: clickSpy,
          set href(_value: string) {},
          set download(_value: string) {},
        } as unknown as HTMLAnchorElement
      }
      return originalCreateElement(tagName)
    }) as typeof document.createElement)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/analysis', component: AnalysisWorkbenchView }],
    })
    await router.push('/analysis?ts_code=600519.SH')
    await router.isReady()

    const wrapper = mount(AnalysisWorkbenchView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const exportButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('导出 Markdown'))
    expect(exportButton).toBeDefined()
    await exportButton!.trigger('click')
    await flushPromises()
    await vi.runAllTimersAsync()

    expect(analysisApi.exportReport).toHaveBeenCalledWith('report-1', 'markdown')
    expect(clickSpy).toHaveBeenCalled()
    expect(appendSpy).toHaveBeenCalled()
    expect(removeSpy).toHaveBeenCalled()
    expect(revokeSpy).toHaveBeenCalledWith('blob:test')
  })
})
