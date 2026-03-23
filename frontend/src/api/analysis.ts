import { requestJson } from './http'
import { openEventSource } from './http'
import type { StockDailySnapshot, StockInstrument } from './stocks'

export type FactorWeightItemResponse = {
  factor_key: string
  factor_label: string
  weight: number
  direction: string
  evidence: string[]
  reason: string
}

export type AnalysisEventResponse = {
  event_id: string
  scope: string
  title: string
  published_at: string | null
  source: string
  macro_topic: string | null
  event_type: string | null
  event_tags: string[] | null
  sentiment_label: string | null
  sentiment_score: number | null
  anchor_trade_date: string | null
  window_return_pct: number | null
  window_volatility: number | null
  abnormal_volume_ratio: number | null
  correlation_score: number | null
  confidence: string | null
  link_status: string | null
}

export type AnalysisReportResponse = {
  id?: string | null
  status: string
  summary: string
  risk_points: string[]
  factor_breakdown: FactorWeightItemResponse[]
  generated_at: string
  trigger_source?: 'manual' | 'watchlist_daily'
  used_web_search?: boolean
  web_search_status?: 'used' | 'disabled' | 'unsupported'
  session_id?: string | null
  started_at?: string | null
  completed_at?: string | null
  content_format?: 'markdown'
  web_sources?: Array<{ title?: string; url?: string; source?: string; published_at?: string | null }>
}

export type StockAnalysisSummaryResponse = {
  ts_code: string
  instrument: StockInstrument | null
  latest_snapshot: StockDailySnapshot | null
  status: 'ready' | 'partial' | 'pending'
  generated_at: string | null
  topic: string | null
  published_from: string | null
  published_to: string | null
  event_count: number
  events: AnalysisEventResponse[]
  report: AnalysisReportResponse | null
}

export type AnalysisReportArchiveListResponse = {
  ts_code: string
  items: AnalysisReportResponse[]
}

export type AnalysisSessionCreateResponse = {
  session_id: string | null
  report_id: string | null
  status: string
  reused: boolean
  cached: boolean
}

export type AnalysisSessionStatusEvent = {
  session_id: string
  status: string
}

export type AnalysisSessionDeltaEvent = {
  session_id: string
  delta: string
  content: string
}

export type AnalysisSessionCompletedEvent = {
  session_id: string
  report_id: string | null
  status: string
}

export type AnalysisSessionErrorEvent = {
  session_id?: string
  detail: string
}

export const analysisApi = {
  async getStockAnalysisSummary(tsCode: string) {
    return requestJson<StockAnalysisSummaryResponse>(
      `/api/analysis/stocks/${encodeURIComponent(tsCode)}/summary`,
    )
  },

  async getStockAnalysisReports(tsCode: string, limit = 10) {
    return requestJson<AnalysisReportArchiveListResponse>(
      `/api/analysis/stocks/${encodeURIComponent(tsCode)}/reports?limit=${limit}`,
    )
  },

  async createAnalysisSession(
    tsCode: string,
    payload: {
      topic?: string | null
      force_refresh?: boolean
      use_web_search?: boolean
      trigger_source?: 'manual' | 'watchlist_daily'
    },
  ) {
    return requestJson<AnalysisSessionCreateResponse>(
      `/api/analysis/stocks/${encodeURIComponent(tsCode)}/sessions`,
      {
        method: 'POST',
        body: payload,
      },
    )
  },

  openAnalysisSessionEvents(
    sessionId: string,
    handlers: {
      onStatus?: (payload: AnalysisSessionStatusEvent) => void
      onReused?: (payload: AnalysisSessionStatusEvent) => void
      onDelta?: (payload: AnalysisSessionDeltaEvent) => void
      onCompleted?: (payload: AnalysisSessionCompletedEvent) => void
      onError?: (payload: AnalysisSessionErrorEvent) => void
    },
    options?: { reused?: boolean },
  ) {
    const query = options?.reused ? '?reused=true' : ''
    return openEventSource(`/api/analysis/sessions/${encodeURIComponent(sessionId)}/events${query}`, {
      status: (payload) => handlers.onStatus?.(payload as AnalysisSessionStatusEvent),
      reused: (payload) => handlers.onReused?.(payload as AnalysisSessionStatusEvent),
      delta: (payload) => handlers.onDelta?.(payload as AnalysisSessionDeltaEvent),
      completed: (payload) => handlers.onCompleted?.(payload as AnalysisSessionCompletedEvent),
      error: (payload) => handlers.onError?.(payload as AnalysisSessionErrorEvent),
    })
  },
}
