import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { MotionPlugin } from '@vueuse/motion'

import { i18n, setAppLocale } from '../i18n'
import { resetPolicySessionCache } from '../stores/policy'
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
  window.sessionStorage.clear()
  resetPolicySessionCache()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const createDeferredResponse = () => {
  let resolve!: (value: ReturnType<typeof jsonResponse>) => void
  const promise = new Promise<ReturnType<typeof jsonResponse>>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}


const createPolicyRouter = async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/policy/documents', component: PolicyDocumentsView }],
  })
  await router.push('/policy/documents')
  await router.isReady()
  return router
}


describe('PolicyDocumentsView', () => {
  it('auto opens the first detail, uses 12-item basic query, and reuses cached detail', async () => {
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
          page_size: 12,
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
    const router = await createPolicyRouter()
    const pinia = createPinia()

    const wrapper = mount(PolicyDocumentsView, {
      global: {
        plugins: [pinia, router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('政策中心')
    expect(wrapper.text()).toContain('国务院关于支持科技创新的若干政策措施')
    expect(wrapper.text()).toContain('国务院')
    expect(wrapper.text()).toContain('为支持科技创新，现提出若干政策措施。')
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('page_size=12')
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('search_scope=basic')
    expect(
      wrapper.get('[data-testid="policy-documents-page"]').attributes('style'),
    ).toContain('--policy-panel-height: 680px')

    const requestCountBeforeReuse = fetchMock.mock.calls.length
    const detailButton = wrapper
      .findAll('button')
      .find((item) => item.text().includes('查看详情'))
    expect(detailButton).toBeDefined()
    await detailButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('fulltext.pdf')
    expect(fetchMock.mock.calls).toHaveLength(requestCountBeforeReuse)
  })

  it('renders policy list and detail inside element scrollbar viewports', async () => {
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
          page_size: 12,
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
          attachments: [],
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = await createPolicyRouter()
    const wrapper = mount(PolicyDocumentsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })

    await flushPromises()

    const listPanel = wrapper.get('[data-testid="policy-list-panel"]')
    const detailPanel = wrapper.get('[data-testid="policy-detail-panel"]')

    expect(listPanel.find('[data-testid="policy-list-scrollbar"]').exists()).toBe(true)
    expect(listPanel.find('.el-scrollbar').exists()).toBe(true)
    expect(detailPanel.find('[data-testid="policy-detail-scrollbar"]').exists()).toBe(true)
    expect(detailPanel.find('.el-scrollbar').exists()).toBe(true)
  })

  it('restores cached content immediately on remount and refreshes in background', async () => {
    const firstFetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          authorities: [{ label: '国务院', value: '国务院' }],
          categories: [],
          macro_topics: [],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              id: 'policy-doc-1',
              source: 'gov_cn',
              title: '缓存中的政策标题',
              summary: '缓存中的政策摘要。',
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
          page_size: 12,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'policy-doc-1',
          source: 'gov_cn',
          title: '缓存中的政策标题',
          summary: '缓存中的政策摘要。',
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
          content_text: '缓存中的政策正文。',
          content_html: null,
          industry_tags: [],
          market_tags: [],
          attachments: [],
        }),
      )
    vi.stubGlobal('fetch', firstFetchMock)

    setAppLocale('zh-CN')
    const firstRouter = await createPolicyRouter()
    const firstWrapper = mount(PolicyDocumentsView, {
      global: {
        plugins: [createPinia(), firstRouter, i18n, ElementPlus, MotionPlugin],
      },
    })
    await flushPromises()
    expect(firstWrapper.text()).toContain('缓存中的政策标题')
    expect(firstWrapper.text()).toContain('缓存中的政策正文。')
    firstWrapper.unmount()

    const deferredFilters = createDeferredResponse()
    const deferredDocuments = createDeferredResponse()
    const secondFetchMock = vi
      .fn()
      .mockReturnValueOnce(deferredFilters.promise)
      .mockReturnValueOnce(deferredDocuments.promise)
    vi.stubGlobal('fetch', secondFetchMock)

    const secondRouter = await createPolicyRouter()
    const secondWrapper = mount(PolicyDocumentsView, {
      global: {
        plugins: [createPinia(), secondRouter, i18n, ElementPlus, MotionPlugin],
      },
    })
    await flushPromises()

    // 关键流程：再次进入页面时优先渲染缓存，但后台仍会静默刷新最新列表和筛选项。
    expect(secondWrapper.text()).toContain('缓存中的政策标题')
    expect(secondWrapper.text()).toContain('缓存中的政策正文。')
    expect(secondFetchMock).toHaveBeenCalledTimes(2)

    deferredFilters.resolve(
      jsonResponse({
        authorities: [{ label: '国务院', value: '国务院' }],
        categories: [],
        macro_topics: [],
      }),
    )
    deferredDocuments.resolve(
      jsonResponse({
        items: [
          {
            id: 'policy-doc-1',
            source: 'gov_cn',
            title: '后台刷新的政策标题',
            summary: '缓存中的政策摘要。',
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
        page_size: 12,
      }),
    )
    await flushPromises()

    expect(secondWrapper.text()).toContain('后台刷新的政策标题')
    expect(secondWrapper.text()).toContain('缓存中的政策正文。')
  })

  it('keeps fulltext search conditions when paging and auto loads the first detail on the new page', async () => {
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
              title: '第一页政策',
              summary: '第一页摘要',
              document_no: '国发〔2026〕1号',
              issuing_authority: '国务院',
              policy_level: 'state_council',
              category: 'industry',
              macro_topic: 'industrial_policy',
              published_at: '2026-03-31T01:00:00Z',
              effective_at: null,
              url: 'https://www.gov.cn/1',
              metadata_status: 'ready',
              projection_status: 'projected',
            },
          ],
          total: 13,
          page: 1,
          page_size: 12,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'policy-doc-1',
          source: 'gov_cn',
          title: '第一页政策',
          summary: '第一页摘要',
          document_no: '国发〔2026〕1号',
          issuing_authority: '国务院',
          policy_level: 'state_council',
          category: 'industry',
          macro_topic: 'industrial_policy',
          published_at: '2026-03-31T01:00:00Z',
          effective_at: null,
          url: 'https://www.gov.cn/1',
          metadata_status: 'ready',
          projection_status: 'projected',
          content_text: '第一页正文',
          content_html: null,
          industry_tags: [],
          market_tags: [],
          attachments: [],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              id: 'policy-doc-1',
              source: 'gov_cn',
              title: '第一页政策',
              summary: '第一页摘要',
              document_no: '国发〔2026〕1号',
              issuing_authority: '国务院',
              policy_level: 'state_council',
              category: 'industry',
              macro_topic: 'industrial_policy',
              published_at: '2026-03-31T01:00:00Z',
              effective_at: null,
              url: 'https://www.gov.cn/1',
              metadata_status: 'ready',
              projection_status: 'projected',
            },
          ],
          total: 13,
          page: 1,
          page_size: 12,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [
            {
              id: 'policy-doc-13',
              source: 'gov_cn',
              title: '第二页政策',
              summary: '第二页摘要',
              document_no: '国发〔2026〕13号',
              issuing_authority: '国务院',
              policy_level: 'state_council',
              category: 'industry',
              macro_topic: 'industrial_policy',
              published_at: '2026-03-19T01:00:00Z',
              effective_at: null,
              url: 'https://www.gov.cn/13',
              metadata_status: 'ready',
              projection_status: 'projected',
            },
          ],
          total: 13,
          page: 2,
          page_size: 12,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'policy-doc-13',
          source: 'gov_cn',
          title: '第二页政策',
          summary: '第二页摘要',
          document_no: '国发〔2026〕13号',
          issuing_authority: '国务院',
          policy_level: 'state_council',
          category: 'industry',
          macro_topic: 'industrial_policy',
          published_at: '2026-03-19T01:00:00Z',
          effective_at: null,
          url: 'https://www.gov.cn/13',
          metadata_status: 'ready',
          projection_status: 'projected',
          content_text: '第二页正文',
          content_html: null,
          industry_tags: [],
          market_tags: [],
          attachments: [],
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    setAppLocale('zh-CN')
    const router = await createPolicyRouter()
    const wrapper = mount(PolicyDocumentsView, {
      global: {
        plugins: [createPinia(), router, i18n, ElementPlus, MotionPlugin],
      },
    })
    await flushPromises()

    await wrapper.get('[data-testid="policy-keyword-input"]').setValue('科技')
    await wrapper.get('[data-testid="policy-fulltext-toggle"]').setValue(true)
    await wrapper.get('[data-testid="policy-search-button"]').trigger('click')
    await flushPromises()

    expect(String(fetchMock.mock.calls[3]?.[0])).toContain('search_scope=fulltext')
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain('keyword=%E7%A7%91%E6%8A%80')
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain('page=1')

    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    expect(pagination.exists()).toBe(true)
    pagination.vm.$emit('current-change', 2)
    await flushPromises()

    expect(String(fetchMock.mock.calls[4]?.[0])).toContain('search_scope=fulltext')
    expect(String(fetchMock.mock.calls[4]?.[0])).toContain('keyword=%E7%A7%91%E6%8A%80')
    expect(String(fetchMock.mock.calls[4]?.[0])).toContain('page=2')
    expect(wrapper.text()).toContain('第二页正文')
  })
})
