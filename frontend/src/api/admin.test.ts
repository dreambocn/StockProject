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

  it('requests evaluation datasets, runs and detail with admin token', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ run_id: 'eval-1' }))
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ run_id: 'eval-1', case_results: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await adminApi.listEvaluationDatasets('admin-access-token')
    await adminApi.createEvaluationRun('admin-access-token', {
      dataset: 'default_research_cases',
      profiles: ['production_current', 'evidence_first_v2'],
    })
    await adminApi.listEvaluationRuns('admin-access-token', {
      dataset: 'default_research_cases',
      promptProfile: 'evidence_first_v2',
      eventType: '政策驱动',
      topic: '政策',
    })
    await adminApi.getEvaluationRun('admin-access-token', 'eval-1')

    const datasetsCall = fetchMock.mock.calls[0] as [string, RequestInit]
    const createCall = fetchMock.mock.calls[1] as [string, RequestInit]
    const runsCall = fetchMock.mock.calls[2] as [string, RequestInit]
    const detailCall = fetchMock.mock.calls[3] as [string, RequestInit]
    expect(datasetsCall[0]).toContain('/api/admin/evaluations/datasets')
    expect(createCall[0]).toContain('/api/admin/evaluations/runs')
    expect(createCall[1].method).toBe('POST')
    expect(createCall[1].body).toBe(
      JSON.stringify({
        dataset: 'default_research_cases',
        profiles: ['production_current', 'evidence_first_v2'],
      }),
    )
    expect(runsCall[0]).toContain('dataset=default_research_cases')
    expect(runsCall[0]).toContain('prompt_profile=evidence_first_v2')
    expect(runsCall[0]).toContain('event_type=%E6%94%BF%E7%AD%96%E9%A9%B1%E5%8A%A8')
    expect(runsCall[0]).toContain('topic=%E6%94%BF%E7%AD%96')
    expect(detailCall[0]).toContain('/api/admin/evaluations/runs/eval-1')
  })
})
