import { requestJson } from './http'
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
  status: string
  summary: string
  risk_points: string[]
  factor_breakdown: FactorWeightItemResponse[]
  generated_at: string
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

export const analysisApi = {
  async getStockAnalysisSummary(tsCode: string) {
    return requestJson<StockAnalysisSummaryResponse>(
      `/api/analysis/stocks/${encodeURIComponent(tsCode)}/summary`,
    )
  },
}
