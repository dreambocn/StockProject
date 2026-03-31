import { afterEach, describe, expect, it, vi } from 'vitest'

import { adminApi } from './admin'

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
})

describe('adminApi', () => {
  it('requests stock full sync with admin token and list status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await adminApi.fetchStocksFull('admin-access-token', {
      listStatus: 'G',
    })

    const firstCall = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(firstCall[0]).toContain('/api/admin/stocks/full?list_status=G')
    expect(firstCall[1].method).toBe('POST')

    const headers = firstCall[1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer admin-access-token')
  })

  it('requests paged stocks from admin database endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await adminApi.listStocks('admin-access-token', {
      keyword: '平安',
      listStatus: 'ALL',
      page: 2,
      pageSize: 50,
    })

    const firstCall = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(firstCall[0]).toContain(
      '/api/admin/stocks?keyword=%E5%B9%B3%E5%AE%89&list_status=ALL&page=2&page_size=50',
    )
    expect(firstCall[1].method).toBe('GET')

    const headers = firstCall[1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer admin-access-token')
  })

  it('requests admin jobs list with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await adminApi.listJobs('admin-access-token', {
      jobType: 'analysis_generate',
      status: 'failed',
      triggerSource: 'manual',
      resourceKey: '600519',
      page: 2,
      pageSize: 10,
    })

    const firstCall = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(firstCall[0]).toContain('/api/admin/jobs?')
    expect(firstCall[0]).toContain('job_type=analysis_generate')
    expect(firstCall[0]).toContain('status=failed')
    expect(firstCall[0]).toContain('trigger_source=manual')
    expect(firstCall[0]).toContain('resource_key=600519')
    expect(firstCall[0]).toContain('page=2')
    expect(firstCall[0]).toContain('page_size=10')
  })

  it('requests admin jobs summary and detail', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ total: 2, status_counts: {}, type_counts: {}, recent_failures: [] }))
      .mockResolvedValueOnce(jsonResponse({ id: 'job-1' }))
    vi.stubGlobal('fetch', fetchMock)

    await adminApi.getJobSummary('admin-access-token')
    await adminApi.getJobDetail('admin-access-token', 'job-1')

    const summaryCall = fetchMock.mock.calls[0] as [string, RequestInit]
    const detailCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(summaryCall[0]).toContain('/api/admin/jobs/summary')
    expect(detailCall[0]).toContain('/api/admin/jobs/job-1')
  })
})
