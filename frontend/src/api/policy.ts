import { requestJson } from './http'
import { buildQueryString } from './query'

export type PolicyDocumentListItem = {
  id: string
  source: string
  title: string
  summary: string | null
  document_no: string | null
  issuing_authority: string | null
  policy_level: string | null
  category: string | null
  macro_topic: string | null
  published_at: string | null
  effective_at: string | null
  url: string
  metadata_status: string
  projection_status: string
}

export type PolicyDocumentAttachment = {
  attachment_url: string
  attachment_name: string | null
  attachment_type: string | null
}

export type PolicyDocumentDetail = PolicyDocumentListItem & {
  content_text: string | null
  content_html: string | null
  attachments: PolicyDocumentAttachment[]
  industry_tags: string[]
  market_tags: string[]
}

export type PolicyFilterOption = {
  label: string
  value: string
}

export type PolicyFilters = {
  authorities: PolicyFilterOption[]
  categories: PolicyFilterOption[]
  macro_topics: PolicyFilterOption[]
}

export type PolicyDocumentPage = {
  items: PolicyDocumentListItem[]
  total: number
  page: number
  page_size: number
}

export type PolicyQuery = {
  authority?: string
  category?: string
  macroTopic?: string
  keyword?: string
  searchScope?: 'basic' | 'fulltext'
  page?: number
  pageSize?: number
}

export type PolicySyncResponse = {
  job_id: string | null
  job_type: string
  status: string
  provider_count: number
  raw_count: number
  normalized_count: number
  inserted_count: number
  updated_count: number
  deduped_count: number
  failed_provider_count: number
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const asString = (value: unknown, fallback = '') =>
  typeof value === 'string' ? value : fallback

const asNullableString = (value: unknown) =>
  typeof value === 'string' ? value : null

const asNumber = (value: unknown, fallback = 0) =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

const asStringArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []

const normalizePolicyDocumentListItem = (item: unknown): PolicyDocumentListItem => {
  if (!isRecord(item)) {
    return {
      id: '',
      source: '',
      title: '',
      summary: null,
      document_no: null,
      issuing_authority: null,
      policy_level: null,
      category: null,
      macro_topic: null,
      published_at: null,
      effective_at: null,
      url: '',
      metadata_status: '',
      projection_status: '',
    }
  }

  return {
    id: asString(item.id),
    source: asString(item.source),
    title: asString(item.title),
    summary: asNullableString(item.summary),
    document_no: asNullableString(item.document_no),
    issuing_authority: asNullableString(item.issuing_authority),
    policy_level: asNullableString(item.policy_level),
    category: asNullableString(item.category),
    macro_topic: asNullableString(item.macro_topic),
    published_at: asNullableString(item.published_at),
    effective_at: asNullableString(item.effective_at),
    url: asString(item.url),
    metadata_status: asString(item.metadata_status),
    projection_status: asString(item.projection_status),
  }
}

const normalizePolicyFilterOption = (item: unknown): PolicyFilterOption => {
  if (!isRecord(item)) {
    return { label: '', value: '' }
  }
  return {
    label: asString(item.label),
    value: asString(item.value),
  }
}

const normalizePolicyDocumentDetail = (item: unknown): PolicyDocumentDetail => {
  const base = normalizePolicyDocumentListItem(item)
  if (!isRecord(item)) {
    return {
      ...base,
      content_text: null,
      content_html: null,
      attachments: [],
      industry_tags: [],
      market_tags: [],
    }
  }

  return {
    ...base,
    content_text: asNullableString(item.content_text),
    content_html: asNullableString(item.content_html),
    attachments: Array.isArray(item.attachments)
      ? item.attachments
          .filter((attachment): attachment is Record<string, unknown> => isRecord(attachment))
          .map((attachment) => ({
            attachment_url: asString(attachment.attachment_url),
            attachment_name: asNullableString(attachment.attachment_name),
            attachment_type: asNullableString(attachment.attachment_type),
          }))
      : [],
    industry_tags: asStringArray(item.industry_tags),
    market_tags: asStringArray(item.market_tags),
  }
}

export const policyApi = {
  async getDocuments(query: PolicyQuery): Promise<PolicyDocumentPage> {
    // 关键流程：在 API 层统一拼接分页和筛选参数，避免视图层重复维护接口兼容细节。
    const search = buildQueryString({
      authority: query.authority || undefined,
      category: query.category || undefined,
      macro_topic: query.macroTopic || undefined,
      keyword: query.keyword || undefined,
      search_scope: query.searchScope ?? 'basic',
      page: query.page ?? 1,
      page_size: query.pageSize ?? 12,
    })
    const payload = await requestJson<unknown>(`/api/policy/documents${search}`)
    if (!isRecord(payload)) {
      return { items: [], total: 0, page: 1, page_size: 12 }
    }
    return {
      items: Array.isArray(payload.items)
        ? payload.items.map(normalizePolicyDocumentListItem)
        : [],
      total: asNumber(payload.total),
      page: asNumber(payload.page, 1),
      page_size: asNumber(payload.page_size, 12),
    }
  },

  async getDocument(documentId: string): Promise<PolicyDocumentDetail> {
    const payload = await requestJson<unknown>(
      `/api/policy/documents/${encodeURIComponent(documentId)}`,
    )
    return normalizePolicyDocumentDetail(payload)
  },

  async getFilters(): Promise<PolicyFilters> {
    const payload = await requestJson<unknown>('/api/policy/filters')
    if (!isRecord(payload)) {
      return { authorities: [], categories: [], macro_topics: [] }
    }
    return {
      authorities: Array.isArray(payload.authorities)
        ? payload.authorities.map(normalizePolicyFilterOption)
        : [],
      categories: Array.isArray(payload.categories)
        ? payload.categories.map(normalizePolicyFilterOption)
        : [],
      macro_topics: Array.isArray(payload.macro_topics)
        ? payload.macro_topics.map(normalizePolicyFilterOption)
        : [],
    }
  },

  async syncDocuments(
    forceRefresh = false,
    accessToken?: string | null,
  ): Promise<PolicySyncResponse> {
    const payload = await requestJson<unknown>('/api/admin/policy/sync', {
      method: 'POST',
      body: { force_refresh: forceRefresh },
      accessToken: accessToken ?? undefined,
    })
    if (!isRecord(payload)) {
      return {
        job_id: null,
        job_type: 'policy_sync',
        status: 'failed',
        provider_count: 0,
        raw_count: 0,
        normalized_count: 0,
        inserted_count: 0,
        updated_count: 0,
        deduped_count: 0,
        failed_provider_count: 0,
      }
    }
    return {
      job_id: asNullableString(payload.job_id),
      job_type: asString(payload.job_type, 'policy_sync'),
      status: asString(payload.status, 'failed'),
      provider_count: asNumber(payload.provider_count),
      raw_count: asNumber(payload.raw_count),
      normalized_count: asNumber(payload.normalized_count),
      inserted_count: asNumber(payload.inserted_count),
      updated_count: asNumber(payload.updated_count),
      deduped_count: asNumber(payload.deduped_count),
      failed_provider_count: asNumber(payload.failed_provider_count),
    }
  },
}
