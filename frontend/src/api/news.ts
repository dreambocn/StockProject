import { requestJson } from './http'
import { buildQueryString } from './query'


export type HotNewsItem = {
  title: string
  summary: string | null
  published_at: string | null
  url: string | null
  source: string
  macro_topic: string
}


export type MacroImpactProfile = {
  topic: string
  affected_assets: string[]
  beneficiary_sectors: string[]
  pressure_sectors: string[]
  a_share_targets: string[]
  a_share_candidates: {
    ts_code: string
    symbol: string
    name: string
    industry: string | null
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
