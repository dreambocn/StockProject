import { requestJson } from './http'
import { buildQueryString } from './query'


export type HotNewsItem = {
  event_id: string | null
  cluster_key: string | null
  providers: string[]
  source_coverage: string
  title: string
  summary: string | null
  published_at: string | null
  url: string | null
  source: string
  macro_topic: string
}

export type AnchorEvent = {
  event_id: string | null
  title: string
  published_at: string | null
  providers: string[]
  source_coverage: string
}

export type MacroImpactProfile = {
  topic: string
  affected_assets: string[]
  beneficiary_sectors: string[]
  pressure_sectors: string[]
  a_share_targets: string[]
  anchor_event: AnchorEvent | null
  a_share_candidates: {
    ts_code: string
    symbol: string
    name: string
    industry: string | null
    relevance_score: number
    match_reasons: string[]
    evidence_summary: string
    source_hit_count: number
  }[]
}


export const newsApi = {
  async getHotNews(limit = 50, topic?: string) {
    const query = buildQueryString({ limit, topic })
    return requestJson<HotNewsItem[]>(`/api/news/hot${query}`)
  },
  async getImpactMap(topic?: string) {
    const query = buildQueryString({ topic })
    return requestJson<MacroImpactProfile[]>(`/api/news/impact-map${query}`)
  },
}
