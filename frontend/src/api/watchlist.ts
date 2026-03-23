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
    return requestJson<WatchlistItemResponse>(`/api/watchlist/items/${encodeURIComponent(tsCode)}`, {
      method: 'PATCH',
      accessToken,
      body: payload,
    })
  },

  deleteWatchlistItem(accessToken: string, tsCode: string) {
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
