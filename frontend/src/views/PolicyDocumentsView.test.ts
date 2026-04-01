import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import { i18n, setAppLocale } from '../i18n'
import PolicyDocumentsView from './PolicyDocumentsView.vue'


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


describe('PolicyDocumentsView', () => {
  it('renders policy document list with filters and detail entry', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          authorities: [{ label: '国务院', value: '国务院' }],
          categories: [{ label: 'industry', value: 'industry' }],
          macro_topics: [{ label: 'industrial_policy', value: 'industrial_policy' }],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              id: 'policy-doc-1',
              source: 'gov_cn',
              title: '国务院关于支持科技创新的若干政策措施',
              summary: '支持科技创新和设备更新。',
              document_no: '国发〔2026〕1号',
              issuing_authority: '国务院',
              policy_level: 'state_council',
              category: 'industry',
              macro_topic: 'industrial_policy',
              published_at: '2026-03-31T01:00:00Z',
              effective_at: null,
              url: 'https://www.gov.cn/zhengce/content/2026-03/31/content_000002.htm',
              metadata_status: 'ready',
              projection_status: 'projected',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              id: 'policy-doc-1',
              source: 'gov_cn',
              title: '国务院关于支持科技创新的若干政策措施',
              summary: '支持科技创新和设备更新。',
              document_no: '国发〔2026〕1号',
              issuing_authority: '国务院',
              policy_level: 'state_council',
              category: 'industry',
              macro_topic: 'industrial_policy',
              published_at: '2026-03-31T01:00:00Z',
              effective_at: null,
              url: 'https://www.gov.cn/zhengce/content/2026-03/31/content_000002.htm',
              metadata_status: 'ready',
              projection_status: 'projected',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'policy-doc-1',
          source: 'gov_cn',
          title: '国务院关于支持科技创新的若干政策措施',
          summary: '支持科技创新和设备更新。',
          document_no: '国发〔2026〕1号',
          issuing_authority: '国务院',
          policy_level: 'state_council',
          category: 'industry',
          macro_topic: 'industrial_policy',
          published_at: '2026-03-31T01:00:00Z',
          effective_at: null,
          url: 'https://www.gov.cn/zhengce/content/2026-03/31/content_000002.htm',
          metadata_status: 'ready',
          projection_status: 'projected',
          content_text: '为支持科技创新，现提出若干政策措施。',
          content_html: null,
          industry_tags: ['ai_computing'],
          market_tags: ['a_share'],
          attachments: [
            {
              attachment_url: 'https://www.gov.cn/policy/fulltext.pdf',
              attachment_name: 'fulltext.pdf',
              attachment_type: 'pdf',
            },
          ],
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/policy/documents', component: PolicyDocumentsView }],
    })
    await router.push('/policy/documents')
    await router.isReady()

    const wrapper = mount(PolicyDocumentsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('政策中心')
    expect(wrapper.text()).toContain('国务院关于支持科技创新的若干政策措施')
    expect(wrapper.text()).toContain('国务院')

    const keywordInput = wrapper.get('[data-testid="policy-keyword-input"]')
    await keywordInput.setValue('科技')
    await wrapper.get('[data-testid="policy-search-button"]').trigger('click')
    await flushPromises()

    const detailButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('查看详情'))
    expect(detailButton).toBeDefined()
    await detailButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('为支持科技创新，现提出若干政策措施。')
    expect(wrapper.text()).toContain('fulltext.pdf')
  })
})
