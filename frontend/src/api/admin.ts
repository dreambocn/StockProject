import { requestJson } from './http'
import { buildQueryString } from './query'

export type AdminUser = {
  id: string
  username: string
  email: string
  is_active: boolean
  user_level: 'user' | 'admin'
  created_at: string
  updated_at: string
  last_login_at: string | null
}

export type CreateAdminUserPayload = {
  username: string
  email: string
  password: string
  user_level: 'user' | 'admin'
}

export type AdminStock = {
  ts_code: string
  symbol: string
  name: string
  area: string | null
  industry: string | null
  fullname: string | null
  enname: string | null
  cnspell: string | null
  market: string | null
  exchange: string | null
  curr_type: string | null
  list_status: string
  list_date: string | null
  delist_date: string | null
  is_hs: string | null
  act_name: string | null
  act_ent_type: string | null
}

export type AdminStockPage = {
  items: AdminStock[]
  total: number
  page: number
  page_size: number
}

export type AdminStockSyncResult = {
  message: string
  total: number
  created: number
  updated: number
  list_statuses: string[]
}

export type AdminJobLinkedEntity = {
  entity_type: string | null
  entity_id: string | null
}

export type AdminJobListItem = {
  id: string
  job_type: string
  status: 'queued' | 'running' | 'success' | 'partial' | 'failed'
  trigger_source: string
  resource_type: string | null
  resource_key: string | null
  summary: string | null
  linked_entity: AdminJobLinkedEntity
  started_at: string | null
  heartbeat_at: string | null
  finished_at: string | null
  duration_ms: number | null
  created_at: string
  updated_at: string
}

export type AdminJobPage = {
  items: AdminJobListItem[]
  total: number
  page: number
  page_size: number
}

export type AdminJobFailureSummary = {
  id: string
  job_type: string
  trigger_source: string
  resource_key: string | null
  error_type: string | null
  error_message: string | null
  finished_at: string | null
}

export type AdminJobSummary = {
  total: number
  status_counts: Record<string, number>
  type_counts: Record<string, number>
  recent_failures: AdminJobFailureSummary[]
}

export type AdminJobDetail = AdminJobListItem & {
  idempotency_key: string | null
  payload_json: Record<string, unknown> | unknown[] | null
  metrics_json: Record<string, unknown> | unknown[] | null
  error_type: string | null
  error_message: string | null
}

export const adminApi = {
  listUsers: (accessToken: string) =>
    // 管理员接口必须携带 access token，权限校验由后端统一处理。
    requestJson<AdminUser[]>('/api/admin/users', {
      method: 'GET',
      accessToken,
    }),

  fetchStocksFull: (
    accessToken: string,
    filters?: {
      listStatus?: string
    },
  ) => {
    const query = buildQueryString({
      list_status: filters?.listStatus,
    })
    // 全量同步会触发后端入库任务，仅用于管理员手动触发。
    return requestJson<AdminStockSyncResult>(`/api/admin/stocks/full${query}`, {
      method: 'POST',
      accessToken,
    })
  },

  listStocks: (
    accessToken: string,
    filters?: {
      keyword?: string
      listStatus?: string
      page?: number
      pageSize?: number
    },
  ) => {
    const query = buildQueryString({
      keyword: filters?.keyword,
      list_status: filters?.listStatus,
      page: filters?.page,
      page_size: filters?.pageSize,
    })
    // 走后台分页接口，避免前端拿到过量数据导致渲染压力。
    return requestJson<AdminStockPage>(`/api/admin/stocks${query}`, {
      method: 'GET',
      accessToken,
    })
  },

  listJobs: (
    accessToken: string,
    filters?: {
      jobType?: string
      status?: string
      triggerSource?: string
      resourceKey?: string
      page?: number
      pageSize?: number
      startedFrom?: string
      startedTo?: string
    },
  ) => {
    const query = buildQueryString({
      job_type: filters?.jobType,
      status: filters?.status,
      trigger_source: filters?.triggerSource,
      resource_key: filters?.resourceKey,
      page: filters?.page,
      page_size: filters?.pageSize,
      started_from: filters?.startedFrom,
      started_to: filters?.startedTo,
    })
    return requestJson<AdminJobPage>(`/api/admin/jobs${query}`, {
      method: 'GET',
      accessToken,
    })
  },

  getJobSummary: (accessToken: string) =>
    requestJson<AdminJobSummary>('/api/admin/jobs/summary', {
      method: 'GET',
      accessToken,
    }),

  getJobDetail: (accessToken: string, jobId: string) =>
    requestJson<AdminJobDetail>(`/api/admin/jobs/${encodeURIComponent(jobId)}`, {
      method: 'GET',
      accessToken,
    }),

  createUser: (accessToken: string, payload: CreateAdminUserPayload) =>
    requestJson<AdminUser>('/api/admin/users', {
      method: 'POST',
      body: payload,
      accessToken,
    }),
}
