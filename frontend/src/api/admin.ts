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

export const adminApi = {
  listUsers: (accessToken: string) =>
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
    return requestJson<AdminStockPage>(`/api/admin/stocks${query}`, {
      method: 'GET',
      accessToken,
    })
  },

  createUser: (accessToken: string, payload: CreateAdminUserPayload) =>
    requestJson<AdminUser>('/api/admin/users', {
      method: 'POST',
      body: payload,
      accessToken,
    }),
}
