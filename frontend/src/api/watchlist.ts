import { requestJson } from './http'
import type { AnalysisReportResponse } from './analysis'
import type { StockInstrument } from './stocks'

export type WatchlistItemResponse = {
  id: string
  ts_code: string
  hourly_sync_enabled: boolean
  daily_analysis_enabled: boolean
  web_search_enabled: boolean
  last_hourly_sync_at: string | null
  last_daily_analysis_at: string | null
  created_at: string
  updated_at: string
  instrument: StockInstrument | null
  latest_report: AnalysisReportResponse | null
}

export type WatchlistResponse = {
  items: WatchlistItemResponse[]
}

export type WatchlistFeedItemResponse = {
  ts_code: string
  instrument: StockInstrument | null
  latest_report: AnalysisReportResponse | null
  last_hourly_sync_at: string | null
  last_daily_analysis_at: string | null
}

export type WatchlistFeedResponse = {
  items: WatchlistFeedItemResponse[]
}

export const watchlistApi = {
  getWatchlist(accessToken: string) {
    // 关注列表必须携带 token，权限校验由后端统一处理。
    return requestJson<WatchlistResponse>('/api/watchlist', {
      accessToken,
    })
  },

  createWatchlistItem(
    accessToken: string,
    payload: {
      ts_code: string
      hourly_sync_enabled?: boolean
      daily_analysis_enabled?: boolean
      web_search_enabled?: boolean
    },
  ) {
    return requestJson<WatchlistItemResponse>('/api/watchlist/items', {
      method: 'POST',
      accessToken,
      body: payload,
    })
  },

  updateWatchlistItem(
    accessToken: string,
    tsCode: string,
    payload: {
      hourly_sync_enabled?: boolean
      daily_analysis_enabled?: boolean
      web_search_enabled?: boolean
    },
  ) {
    // PATCH 仅更新传入字段，避免覆盖未修改的开关状态。
    return requestJson<WatchlistItemResponse>(`/api/watchlist/items/${encodeURIComponent(tsCode)}`, {
      method: 'PATCH',
      accessToken,
      body: payload,
    })
  },

  deleteWatchlistItem(accessToken: string, tsCode: string) {
    // 删除只影响当前用户关注记录，不影响股票主数据。
    return requestJson<{ message: string }>(`/api/watchlist/items/${encodeURIComponent(tsCode)}`, {
      method: 'DELETE',
      accessToken,
    })
  },

  getWatchlistFeed(accessToken: string) {
    return requestJson<WatchlistFeedResponse>('/api/watchlist/feed', {
      accessToken,
    })
  },
}
