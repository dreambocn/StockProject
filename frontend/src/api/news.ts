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

export type CandidateSourceBreakdownItem = {
  source: string
  count: number
}

export type CandidateEvidenceItem = {
  ts_code: string
  symbol: string
  name: string
  evidence_kind: string
  title: string
  summary: string | null
  published_at: string | null
  url: string | null
  source: string
}

export type MacroImpactCandidate = {
  ts_code: string
  symbol: string
  name: string
  industry: string | null
  relevance_score: number
  match_reasons: string[]
  evidence_summary: string
  source_hit_count: number
  source_breakdown: CandidateSourceBreakdownItem[]
  freshness_score: number
  candidate_confidence: string
  evidence_items: CandidateEvidenceItem[]
}

export type MacroImpactProfile = {
  topic: string
  affected_assets: string[]
  beneficiary_sectors: string[]
  pressure_sectors: string[]
  a_share_targets: string[]
  anchor_event: AnchorEvent | null
  a_share_candidates: MacroImpactCandidate[]
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const asString = (value: unknown, fallback = '') =>
  typeof value === 'string' ? value : fallback

const asNullableString = (value: unknown) =>
  typeof value === 'string' ? value : null

const asStringArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []

const asNumber = (value: unknown, fallback = 0) =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

const normalizeCandidateSourceBreakdownItem = (item: unknown): CandidateSourceBreakdownItem => {
  if (!isRecord(item)) {
    return { source: '', count: 0 }
  }
  return {
    source: asString(item.source),
    count: asNumber(item.count),
  }
}

const normalizeCandidateEvidenceItem = (item: unknown): CandidateEvidenceItem => {
  if (!isRecord(item)) {
    return {
      ts_code: '',
      symbol: '',
      name: '',
      evidence_kind: 'research_report',
      title: '',
      summary: null,
      published_at: null,
      url: null,
      source: '',
    }
  }

  return {
    ts_code: asString(item.ts_code),
    symbol: asString(item.symbol),
    name: asString(item.name),
    evidence_kind: asString(item.evidence_kind, 'research_report'),
    title: asString(item.title),
    summary: asNullableString(item.summary),
    published_at: asNullableString(item.published_at),
    url: asNullableString(item.url),
    source: asString(item.source),
  }
}

const normalizeAnchorEvent = (value: unknown): AnchorEvent | null => {
  if (!isRecord(value)) {
    return null
  }
  return {
    event_id: asNullableString(value.event_id),
    title: asString(value.title),
    published_at: asNullableString(value.published_at),
    providers: asStringArray(value.providers),
    source_coverage: asString(value.source_coverage),
  }
}

const normalizeHotNewsItem = (item: unknown): HotNewsItem => {
  if (!isRecord(item)) {
    return {
      event_id: null,
      cluster_key: null,
      providers: [],
      source_coverage: '',
      title: '',
      summary: null,
      published_at: null,
      url: null,
      source: '',
      macro_topic: 'other',
    }
  }

  return {
    event_id: asNullableString(item.event_id),
    cluster_key: asNullableString(item.cluster_key),
    providers: asStringArray(item.providers),
    source_coverage: asString(item.source_coverage),
    title: asString(item.title),
    summary: asNullableString(item.summary),
    published_at: asNullableString(item.published_at),
    url: asNullableString(item.url),
    source: asString(item.source),
    macro_topic: asString(item.macro_topic, 'other'),
  }
}

const normalizeMacroImpactCandidate = (item: unknown): MacroImpactCandidate => {
  if (!isRecord(item)) {
    return {
      ts_code: '',
      symbol: '',
      name: '',
      industry: null,
      relevance_score: 0,
      match_reasons: [],
      evidence_summary: '',
      source_hit_count: 0,
      source_breakdown: [],
      freshness_score: 0,
      candidate_confidence: '',
      evidence_items: [],
    }
  }

  return {
    ts_code: asString(item.ts_code),
    symbol: asString(item.symbol),
    name: asString(item.name),
    industry: asNullableString(item.industry),
    relevance_score: asNumber(item.relevance_score),
    match_reasons: asStringArray(item.match_reasons),
    evidence_summary: asString(item.evidence_summary),
    source_hit_count: asNumber(item.source_hit_count),
    source_breakdown: Array.isArray(item.source_breakdown)
      ? item.source_breakdown.map(normalizeCandidateSourceBreakdownItem)
      : [],
    freshness_score: asNumber(item.freshness_score),
    candidate_confidence: asString(item.candidate_confidence),
    evidence_items: Array.isArray(item.evidence_items)
      ? item.evidence_items.map(normalizeCandidateEvidenceItem)
      : [],
  }
}

const normalizeMacroImpactProfile = (item: unknown): MacroImpactProfile => {
  if (!isRecord(item)) {
    return {
      topic: 'other',
      affected_assets: [],
      beneficiary_sectors: [],
      pressure_sectors: [],
      a_share_targets: [],
      anchor_event: null,
      a_share_candidates: [],
    }
  }

  return {
    topic: asString(item.topic, 'other'),
    affected_assets: asStringArray(item.affected_assets),
    beneficiary_sectors: asStringArray(item.beneficiary_sectors),
    pressure_sectors: asStringArray(item.pressure_sectors),
    a_share_targets: asStringArray(item.a_share_targets),
    // 关键流程：在 API 层统一补齐旧 payload 字段，避免把兼容判断扩散到视图层。
    anchor_event: normalizeAnchorEvent(item.anchor_event),
    a_share_candidates: Array.isArray(item.a_share_candidates)
      ? item.a_share_candidates.map(normalizeMacroImpactCandidate)
      : [],
  }
}

export const newsApi = {
  async getHotNews(limit = 50, topic?: string) {
    const query = buildQueryString({ limit, topic })
    const payload = await requestJson<unknown>(`/api/news/hot${query}`)
    return Array.isArray(payload) ? payload.map(normalizeHotNewsItem) : []
  },
  async getImpactMap(topic?: string, candidateEvidenceLimit?: number) {
    const query = buildQueryString({ topic, candidate_evidence_limit: candidateEvidenceLimit })
    const payload = await requestJson<unknown>(`/api/news/impact-map${query}`)
    return Array.isArray(payload) ? payload.map(normalizeMacroImpactProfile) : []
  },
}
