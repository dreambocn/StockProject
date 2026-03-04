import { requestJson } from './http'


export type StockListItem = {
  ts_code: string
  symbol: string
  name: string
  fullname: string | null
  exchange: string | null
  close: number | null
  pct_chg: number | null
  trade_date: string | null
}


export type StockInstrument = {
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


export type StockDailySnapshot = {
  ts_code: string
  trade_date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  pre_close: number | null
  change: number | null
  pct_chg: number | null
  vol: number | null
  amount: number | null
  turnover_rate: number | null
  volume_ratio: number | null
  pe: number | null
  pb: number | null
  total_mv: number | null
  circ_mv: number | null
}


export type StockDetail = {
  instrument: StockInstrument
  latest_snapshot: StockDailySnapshot | null
}


const buildQueryString = (params: Record<string, string | number | undefined>) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === '') {
      return
    }
    query.set(key, String(value))
  })
  const queryString = query.toString()
  return queryString ? `?${queryString}` : ''
}


export const stocksApi = {
  async listStocks(keyword?: string, listStatus?: string, page = 1, pageSize = 20) {
    const query = buildQueryString({
      keyword,
      list_status: listStatus,
      page,
      page_size: pageSize,
    })
    return requestJson<StockListItem[]>(`/api/stocks${query}`)
  },
  async getStockDetail(tsCode: string) {
    return requestJson<StockDetail>(`/api/stocks/${encodeURIComponent(tsCode)}`)
  },
  async getStockDaily(tsCode: string, limit = 60) {
    const query = buildQueryString({ limit })
    return requestJson<StockDailySnapshot[]>(
      `/api/stocks/${encodeURIComponent(tsCode)}/daily${query}`,
    )
  },
}
