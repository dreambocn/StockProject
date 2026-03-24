import { afterEach, describe, expect, it, vi } from 'vitest'

import { evaluationsApi } from './evaluations'


const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})


describe('evaluationsApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('requests admin evaluation catalog with access token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        datasets: [],
        experiment_groups: [],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await evaluationsApi.getCatalog('admin-token')

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toContain('/api/admin/evaluations/catalog')
    expect(call[1].headers).toMatchObject({
      Authorization: 'Bearer admin-token',
    })
  })

  it('builds overview query with dataset, group, and optional run ids', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        empty: true,
        dataset: null,
        experiment_group_key: 'prompt_profile_compare_v1',
        baseline_run: null,
        candidate_run: null,
        metric_cards: {},
        bar_chart: {
          categories: [],
          baseline_series: [],
          candidate_series: [],
        },
        distribution_chart: {
          improved: 0,
          unchanged: 0,
          regressed: 0,
        },
        top_improved_cases: [],
        top_regressed_cases: [],
        recent_cases: [],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await evaluationsApi.getOverview('admin-token', {
      datasetKey: 'analysis_eval_dataset_v1',
      experimentGroupKey: 'prompt_profile_compare_v1',
      baselineRunId: 'baseline-1',
      candidateRunId: 'optimized-1',
    })

    const call = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toContain(
      '/api/admin/evaluations/overview?dataset_key=analysis_eval_dataset_v1',
    )
    expect(call[0]).toContain('experiment_group_key=prompt_profile_compare_v1')
    expect(call[0]).toContain('baseline_run_id=baseline-1')
    expect(call[0]).toContain('candidate_run_id=optimized-1')
    expect(call[1].method).toBe('GET')
  })
})
