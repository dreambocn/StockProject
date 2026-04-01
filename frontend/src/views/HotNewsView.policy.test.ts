import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import HotNewsView from './HotNewsView.vue'
import { newsApi } from '../api/news'
import { policyApi } from '../api/policy'
import { i18n, setAppLocale } from '../i18n'


afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})


describe('HotNewsView related policies', () => {
  it('renders related policy documents in hot news impact panel', async () => {
    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/news/hot', component: HotNewsView }],
    })
    await router.push({ path: '/news/hot', query: { topic: 'regulation_policy' } })
    await router.isReady()

    vi.spyOn(newsApi, 'getHotNews').mockResolvedValue([
      {
        event_id: 'evt-hot-policy',
        cluster_key: 'cluster-hot-policy',
        providers: ['akshare'],
        source_coverage: 'AK',
        title: '监管口径出现边际优化',
        summary: '市场关注政策边际变化。',
        published_at: '2026-03-31T08:00:00Z',
        url: 'https://finance.example.com/hot-policy',
        source: 'eastmoney_global',
        macro_topic: 'regulation_policy',
      },
    ])
    vi.spyOn(newsApi, 'getImpactMap').mockResolvedValue([])
    vi.spyOn(policyApi, 'getDocuments').mockResolvedValue({
      items: [
        {
          id: 'policy-doc-1',
          source: 'gov_cn',
          title: '国务院关于优化科技监管环境的若干政策措施',
          summary: '提出进一步优化创新监管环境。',
          document_no: '国发〔2026〕1号',
          issuing_authority: '国务院',
          policy_level: 'state_council',
          category: 'industry',
          macro_topic: 'regulation_policy',
          published_at: '2026-03-31T01:00:00Z',
          effective_at: null,
          url: 'https://www.gov.cn/zhengce/content/2026-03/31/content_000002.htm',
          metadata_status: 'ready',
          projection_status: 'projected',
        },
      ],
      total: 1,
      page: 1,
      page_size: 3,
    })

    const wrapper = mount(HotNewsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('相关政策')
    expect(wrapper.text()).toContain('国务院关于优化科技监管环境的若干政策措施')
    expect(wrapper.text()).toContain('国务院')
  })
})
