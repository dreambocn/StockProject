import { afterEach, describe, expect, it, vi } from 'vitest'

import { newsApi } from './news'

const jsonResponse = (payload: unknown) => ({
  ok: true,
  status: 200,
  headers: {
    get: () => 'application/json',
  },
  json: async () => payload,
})

describe('newsApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('normalizes legacy hot news payload fields', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            title: '旧版热点',
            summary: null,
            published_at: null,
            url: null,
            source: 'legacy_source',
          },
        ]),
      ),
    )

    const result = await newsApi.getHotNews()

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      event_id: null,
      cluster_key: null,
      providers: [],
      source_coverage: '',
      title: '旧版热点',
      source: 'legacy_source',
      macro_topic: 'other',
    })
  })

  it('normalizes legacy impact map payload fields', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            topic: 'commodity_supply',
            affected_assets: ['原油'],
            beneficiary_sectors: ['油气开采'],
            pressure_sectors: ['航空运输'],
            a_share_targets: ['中国海油'],
            a_share_candidates: [
              {
                ts_code: '600938.SH',
                symbol: '600938',
                name: '中国海油',
                industry: '石油开采',
                relevance_score: 45,
                match_reasons: ['命中主题目标股'],
                evidence_summary: '命中主题目标股',
                source_hit_count: 1,
              },
            ],
          },
        ]),
      ),
    )

    const result = await newsApi.getImpactMap()

    expect(result).toHaveLength(1)
    const firstProfile = result[0]!
    const firstCandidate = firstProfile.a_share_candidates[0]!
    expect(firstProfile.anchor_event).toBeNull()
    expect(firstCandidate).toMatchObject({
      source_breakdown: [],
      freshness_score: 0,
      candidate_confidence: '',
      evidence_items: [],
    })
  })
})
