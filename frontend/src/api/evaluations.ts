import { requestJson } from './http'
import { buildQueryString } from './query'

export type EvaluationDataset = {
  id: string
  dataset_key: string
  label: string
  description?: string | null
  sample_count: number
  date_from?: string | null
  date_to?: string | null
}

export type EvaluationRunSummary = {
  id: string
  run_key: string
  experiment_group_key: string
  variant_key: 'baseline' | 'optimized'
  variant_label: string
  prompt_profile_key: string
  model_name: string
  sample_count: number
  event_top1_hit_rate: number
  factor_top1_accuracy: number
  citation_metadata_completeness_rate: number
  avg_latency_ms: number
  created_at: string
}

export type EvaluationExperimentGroup = {
  dataset_key: string
  experiment_group_key: string
  latest_baseline_run?: EvaluationRunSummary | null
  latest_candidate_run?: EvaluationRunSummary | null
  baseline_runs: EvaluationRunSummary[]
  candidate_runs: EvaluationRunSummary[]
}

export type EvaluationCatalogResponse = {
  datasets: EvaluationDataset[]
  experiment_groups: EvaluationExperimentGroup[]
}

export type EvaluationMetricCard = {
  metric_key: string
  label: string
  unit: string
  baseline_value: number
  candidate_value: number
}

export type EvaluationCaseComparison = {
  case_key: string
  ts_code: string
  topic?: string | null
  anchor_event_title: string
  expected_top_factor_key: string
  notes?: string | null
  baseline_score: number
  candidate_score: number
  score_delta: number
  classification: 'improved' | 'regressed' | 'unchanged'
  baseline_top_event_title?: string | null
  candidate_top_event_title?: string | null
  baseline_top_factor_key?: string | null
  candidate_top_factor_key?: string | null
  baseline_citation_metadata_completeness_rate: number
  candidate_citation_metadata_completeness_rate: number
  baseline_latency_ms: number
  candidate_latency_ms: number
}

export type EvaluationOverviewResponse = {
  empty: boolean
  dataset: EvaluationDataset | null
  experiment_group_key: string
  baseline_run: EvaluationRunSummary | null
  candidate_run: EvaluationRunSummary | null
  metric_cards: Record<string, EvaluationMetricCard>
  bar_chart: {
    categories: string[]
    baseline_series: number[]
    candidate_series: number[]
  }
  distribution_chart: {
    improved: number
    unchanged: number
    regressed: number
  }
  top_improved_cases: EvaluationCaseComparison[]
  top_regressed_cases: EvaluationCaseComparison[]
  recent_cases: EvaluationCaseComparison[]
}

export type EvaluationCaseDetailResponse = {
  case: {
    case_key: string
    ts_code: string
    topic?: string | null
    anchor_event_title: string
    expected_top_factor_key: string
    notes?: string | null
  }
  baseline_run: EvaluationRunSummary
  candidate_run: EvaluationRunSummary
  baseline_result: {
    event_top1_hit: boolean
    factor_top1_hit: boolean
    citation_metadata_completeness_rate: number
    latency_ms: number
    top_event_title?: string | null
    top_factor_key?: string | null
    web_source_count: number
    result_snapshot?: {
      summary?: string
      risk_points?: string[]
      factor_breakdown?: Array<Record<string, unknown>>
      web_sources?: Array<Record<string, unknown>>
    } | null
    case_score: number
    classification: 'improved' | 'regressed' | 'unchanged'
  }
  candidate_result: {
    event_top1_hit: boolean
    factor_top1_hit: boolean
    citation_metadata_completeness_rate: number
    latency_ms: number
    top_event_title?: string | null
    top_factor_key?: string | null
    web_source_count: number
    result_snapshot?: {
      summary?: string
      risk_points?: string[]
      factor_breakdown?: Array<Record<string, unknown>>
      web_sources?: Array<Record<string, unknown>>
    } | null
    case_score: number
    classification: 'improved' | 'regressed' | 'unchanged'
  }
}

export const evaluationsApi = {
  getCatalog: (accessToken: string) =>
    requestJson<EvaluationCatalogResponse>('/api/admin/evaluations/catalog', {
      method: 'GET',
      accessToken,
    }),

  getOverview: (
    accessToken: string,
    options: {
      datasetKey: string
      experimentGroupKey: string
      baselineRunId?: string | null
      candidateRunId?: string | null
    },
  ) => {
    const query = buildQueryString({
      dataset_key: options.datasetKey,
      experiment_group_key: options.experimentGroupKey,
      baseline_run_id: options.baselineRunId || undefined,
      candidate_run_id: options.candidateRunId || undefined,
    })
    return requestJson<EvaluationOverviewResponse>(
      `/api/admin/evaluations/overview${query}`,
      {
        method: 'GET',
        accessToken,
      },
    )
  },

  getCaseDetail: (
    accessToken: string,
    caseKey: string,
    options: {
      baselineRunId: string
      candidateRunId: string
    },
  ) => {
    const query = buildQueryString({
      baseline_run_id: options.baselineRunId,
      candidate_run_id: options.candidateRunId,
    })
    return requestJson<EvaluationCaseDetailResponse>(
      `/api/admin/evaluations/cases/${encodeURIComponent(caseKey)}${query}`,
      {
        method: 'GET',
        accessToken,
      },
    )
  },
}
