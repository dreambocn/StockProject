import { afterEach, describe, expect, it, vi } from 'vitest'

import { policyApi } from './policy'


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


describe('policyApi', () => {
  it('requests policy documents with filters, search scope and normalizes the page payload', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
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
        page: 2,
        page_size: 12,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const payload = await policyApi.getDocuments({
      authority: '国务院',
      keyword: '科技',
      searchScope: 'basic',
      page: 2,
      pageSize: 12,
    })

    expect(payload.total).toBe(1)
    expect(payload.items[0]?.issuing_authority).toBe('国务院')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/policy/documents?')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('authority=%E5%9B%BD%E5%8A%A1%E9%99%A2')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('keyword=%E7%A7%91%E6%8A%80')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('search_scope=basic')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('page=2')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('page_size=12')
  })

  it('sends access token when admin sync is triggered', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse({
        job_id: 'job-1',
        job_type: 'policy_sync',
        status: 'success',
        provider_count: 6,
        raw_count: 10,
        normalized_count: 10,
        inserted_count: 8,
        updated_count: 2,
        deduped_count: 0,
        failed_provider_count: 0,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await policyApi.syncDocuments(true, 'token-123')

    expect(fetchMock.mock.calls[0]?.[1]?.headers).toMatchObject({
      Authorization: 'Bearer token-123',
    })
  })
})
