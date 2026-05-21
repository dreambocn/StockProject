import type {
  AnalysisEventResponse,
  AnalysisReportResponse,
  AnalysisSourceItem,
} from '../../api/analysis'

type WebSourceItem = NonNullable<AnalysisReportResponse['web_sources']>[number]

export const buildReportRuntimeMeta = (report: AnalysisReportResponse | null) => {
  if (!report) {
    return []
  }
  return [
    report.prompt_version ? `提示词 ${report.prompt_version}` : null,
    report.model_name ? `模型 ${report.model_name}` : null,
    report.reasoning_effort ? `推理 ${report.reasoning_effort}` : null,
    typeof report.token_usage_input === 'number' ? `输入 Token ${report.token_usage_input}` : null,
    typeof report.token_usage_output === 'number' ? `输出 Token ${report.token_usage_output}` : null,
    report.failure_type ? `失败类型 ${report.failure_type}` : null,
    report.session_id ? `会话 ${report.session_id}` : null,
  ].filter((item): item is string => Boolean(item))
}

export const buildHistoryDiffHints = (
  current: AnalysisReportResponse | null,
  previous: AnalysisReportResponse | null,
  formatDateTime: (value: string | null | undefined) => string,
) => {
  if (!current || !previous) {
    return []
  }
  const currentConfidence = current.decision_confidence || '--'
  const previousConfidence = previous.decision_confidence || '--'
  const currentHypothesis = current.selected_hypothesis || '--'
  const previousHypothesis = previous.selected_hypothesis || '--'
  const currentEventCount = current.evidence_event_count ?? current.evidence_events?.length ?? 0
  const previousEventCount = previous.evidence_event_count ?? previous.evidence_events?.length ?? 0
  return [
    `生成时间：${formatDateTime(previous.generated_at)} → ${formatDateTime(current.generated_at)}`,
    `事件数：${previousEventCount} → ${currentEventCount}`,
    `采纳假设：${previousHypothesis} → ${currentHypothesis}`,
    `置信度：${previousConfidence} → ${currentConfidence}`,
  ]
}

export const buildFallbackSourceItems = (
  events: AnalysisEventResponse[],
  webSources: WebSourceItem[],
  dataMissingText: string,
): AnalysisSourceItem[] => {
  const eventItems = events.map((event) => ({
    id: `event-${event.event_id}`,
    source_kind: event.scope === 'policy' || event.event_type === 'policy'
      ? 'policy_document'
      : 'structured_event',
    title: event.title,
    source_name: event.source,
    quality_status: event.link_status === 'linked' ? 'verified' : 'unavailable',
    published_at: event.published_at,
    metadata_status: event.published_at ? 'enriched' : 'unavailable',
    evidence_id: event.event_id,
  }) satisfies AnalysisSourceItem)
  const webItems = webSources.map((item, index) => ({
    id: `web-${item.url || index}`,
    source_kind: 'web_reference',
    title: item.title || item.url || dataMissingText,
    source_name: item.source || item.domain || null,
    url: item.url || null,
    snippet: item.snippet || null,
    quality_status: item.metadata_status === 'enriched'
      ? 'enriched'
      : item.metadata_status === 'domain_inferred'
        ? 'domain_inferred'
        : 'unavailable',
    published_at: item.published_at ?? null,
    domain: item.domain ?? null,
    metadata_status: item.metadata_status ?? null,
  }) satisfies AnalysisSourceItem)
  return [...eventItems, ...webItems]
}

export const sortSourceItems = (items: AnalysisSourceItem[]) => {
  const kindRank: Record<AnalysisSourceItem['source_kind'], number> = {
    policy_document: 0,
    structured_event: 1,
    market_data: 2,
    web_reference: 3,
  }
  const qualityRank: Record<string, number> = {
    verified: 0,
    enriched: 1,
    domain_inferred: 2,
    unavailable: 3,
  }
  return [...items].sort((left, right) => {
    const kindDelta = (kindRank[left.source_kind] ?? 9) - (kindRank[right.source_kind] ?? 9)
    if (kindDelta !== 0) {
      return kindDelta
    }
    const qualityDelta =
      (qualityRank[left.quality_status || 'unavailable'] ?? 9)
      - (qualityRank[right.quality_status || 'unavailable'] ?? 9)
    if (qualityDelta !== 0) {
      return qualityDelta
    }
    return (right.published_at ? 1 : 0) - (left.published_at ? 1 : 0)
  })
}

export const buildUnifiedSourceItems = (
  report: AnalysisReportResponse | null,
  fallbackItems: AnalysisSourceItem[],
) => {
  const explicitItems = report?.source_items ?? []
  return sortSourceItems(explicitItems.length > 0 ? explicitItems : fallbackItems)
}
