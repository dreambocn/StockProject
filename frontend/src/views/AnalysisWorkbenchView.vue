<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import MarkdownContent from '../components/MarkdownContent.vue'
import {
  analysisApi,
  type AnalysisReportResponse,
  type AnalysisEventResponse,
  type AnalysisPipelineRoleResponse,
  type StockAnalysisSummaryResponse,
} from '../api/analysis'
import { watchlistApi, type WatchlistItemResponse } from '../api/watchlist'
import { useAuthStore } from '../stores/auth'

type EventFilterKey = 'all' | 'high-related' | 'policy' | 'announcement' | 'news' | 'pending'
type SourceKind = 'watchlist' | 'hot_news' | 'stock_detail' | 'direct'
type AnalysisViewMode = 'events' | 'factors' | 'pipeline' | 'sources'
type ReportEvidencePayload = {
  event_count: number
  events: AnalysisEventResponse[]
}

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const authStore = useAuthStore()

const summary = ref<StockAnalysisSummaryResponse | null>(null)
const reportArchives = ref<AnalysisReportResponse[]>([])
const loading = ref(false)
const errorMessage = ref('')
const selectedEventFilter = ref<EventFilterKey>('all')
const showAllFactors = ref(false)
const showAllEvents = ref(false)
const selectedReportId = ref<string | null>(null)
const streamingMarkdown = ref('')
const streaming = ref(false)
const streamingStageMessage = ref('')
const lastHeartbeatValue = ref('')
const lastHeartbeatObservedAt = ref<number | null>(null)
const exportLoading = ref(false)
const useWebSearch = ref(false)
const analysisViewMode = ref<AnalysisViewMode>('events')
const webSearchInherited = ref(false)
const webSearchSeededTsCode = ref('')
const watchlistLoading = ref(false)
const watchlistItem = ref<WatchlistItemResponse | null>(null)
const expandedRolePayloads = ref<Record<string, boolean>>({})
// 通过递增版本号标识“本轮加载”，用于拦截并发返回的过期数据。
const workbenchLoadVersion = ref(0)
const reportEvidenceCache = ref<Record<string, ReportEvidencePayload>>({})
const activeEvidenceEvents = ref<AnalysisEventResponse[]>([])
const activeEvidenceTotal = ref(0)

let stopSessionStream: (() => void) | null = null
let sessionPollTimer: ReturnType<typeof window.setTimeout> | null = null
let activePollingToken = 0
let activeEvidenceLoadToken = 0

const stopStreaming = () => {
  stopSessionStream?.()
  stopSessionStream = null
  if (sessionPollTimer !== null) {
    window.clearTimeout(sessionPollTimer)
    sessionPollTimer = null
  }
  activePollingToken += 1
  streamingStageMessage.value = ''
  lastHeartbeatValue.value = ''
  lastHeartbeatObservedAt.value = null
}

// 仅允许最新请求写回界面，避免路由切换后的旧响应覆盖新状态。
const isLatestWorkbenchRequest = (requestVersion: number) =>
  requestVersion === workbenchLoadVersion.value

const readQueryString = (value: unknown) => {
  if (Array.isArray(value)) {
    return String(value[0] ?? '').trim()
  }
  return String(value ?? '').trim()
}

const parseTime = (value: string | null | undefined) => {
  if (!value) {
    return null
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return null
  }
  return parsed
}

const formatDateTime = (value: string | null | undefined) => {
  const parsed = parseTime(value)
  if (!parsed) {
    return t('analysisWorkbench.dataMissing')
  }

  return new Intl.DateTimeFormat(locale.value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(parsed)
}

const formatStructuredSourceProvider = (provider: string | null | undefined) => {
  const normalized = String(provider ?? '').trim().toLowerCase()
  if (!normalized) {
    return t('analysisWorkbench.sourceProviders.default')
  }

  // 关键流程：把内部 provider 标识转换为前端文案，避免把实现细节直接暴露给用户。
  const providerLabelMap: Record<string, string> = {
    akshare: t('analysisWorkbench.sourceProviders.akshare'),
    tushare: t('analysisWorkbench.sourceProviders.tushare'),
    policy_document: t('analysisWorkbench.sourceProviders.policyDocument'),
  }
  return providerLabelMap[normalized] ?? provider
}

const formatPrice = (value: number | null | undefined) => {
  if (typeof value !== 'number') {
    return t('analysisWorkbench.dataMissing')
  }
  return `¥${value.toLocaleString(locale.value, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

const formatPercent = (value: number | null | undefined, digits = 2) => {
  if (typeof value !== 'number') {
    return t('analysisWorkbench.dataMissing')
  }
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}%`
}

const formatWeight = (value: number | null | undefined) => {
  if (typeof value !== 'number') {
    return t('analysisWorkbench.dataMissing')
  }
  return `${(value * 100).toFixed(1)}%`
}

const formatMetricNumber = (value: number | null | undefined, digits = 2) => {
  if (typeof value !== 'number') {
    return t('analysisWorkbench.dataMissing')
  }
  return value.toFixed(digits)
}

const getCorrelationPercent = (value: number | null | undefined) => {
  if (typeof value !== 'number') {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(value * 100)))
}

const hasCorrelationMetric = (value: number | null | undefined) => typeof value === 'number'

const resolveRoundedMetricSignature = (value: number, fractionDigits = 2) => value.toFixed(fractionDigits)

const hasUsefulMetricDifference = (
  events: AnalysisEventResponse[],
  selector: (event: AnalysisEventResponse) => number | null | undefined,
  fractionDigits = 2,
) => {
  const values = events
    .map(selector)
    .filter((value): value is number => typeof value === 'number' && !Number.isNaN(value))
  if (values.length < 2) {
    return false
  }
  return new Set(values.map((value) => resolveRoundedMetricSignature(value, fractionDigits))).size > 1
}

const translateStatus = (value: StockAnalysisSummaryResponse['status'] | string | null | undefined) => {
  if (!value) {
    return t('analysisWorkbench.pendingStatus')
  }
  return t(`analysisWorkbench.statusText.${value}`, value)
}

const translateSentiment = (value: string | null | undefined) => {
  if (!value) {
    return t('analysisWorkbench.dataMissing')
  }
  return t(`analysisWorkbench.sentimentText.${value}`, value)
}

const translateConfidence = (value: string | null | undefined) => {
  if (!value) {
    return t('analysisWorkbench.dataMissing')
  }
  return t(`analysisWorkbench.confidenceText.${value}`, value)
}

const translateRoleStatus = (value: string | null | undefined) => {
  if (!value) {
    return t('analysisWorkbench.roleStatusText.queued')
  }
  return t(`analysisWorkbench.roleStatusText.${value}`, value)
}

const translateTriggerSource = (value: string | null | undefined) => {
  if (!value) {
    return t('analysisWorkbench.triggerSourceText.manual')
  }
  return t(`analysisWorkbench.triggerSourceText.${value}`, value)
}

const translateWebSearchStatus = (value: string | null | undefined) => {
  const normalizedValue = value || 'disabled'
  return t(`analysisWorkbench.webSearchStatusText.${normalizedValue}`, normalizedValue)
}

const translateWebSourceMetadataStatus = (value: string | null | undefined) => {
  const normalizedValue = value || 'unavailable'
  return t(`analysisWorkbench.webSourceStatusText.${normalizedValue}`, normalizedValue)
}

const confidenceRank = (value: string | null | undefined) => {
  if (value === 'high') {
    return 3
  }
  if (value === 'medium') {
    return 2
  }
  if (value === 'low') {
    return 1
  }
  return 0
}

const tsCode = computed(() => readQueryString(route.query.ts_code).toUpperCase())
const source = computed(() => readQueryString(route.query.source))
const topicContext = computed(() => readQueryString(route.query.topic))
const eventId = computed(() => readQueryString(route.query.event_id))
const eventTitle = computed(() => readQueryString(route.query.event_title))
const hasTsCode = computed(() => Boolean(tsCode.value))

const sourceKind = computed<SourceKind>(() => {
  if (source.value === 'watchlist') {
    return 'watchlist'
  }
  if (source.value === 'hot_news') {
    return 'hot_news'
  }
  if (source.value === 'stock_detail') {
    return 'stock_detail'
  }
  return 'direct'
})

const sourceLabel = computed(() => t(`analysisWorkbench.sourceText.${sourceKind.value}`))

const displayName = computed(() => summary.value?.instrument?.name ?? tsCode.value)
const displayStatus = computed(() => translateStatus(summary.value?.status))
const generatedAtLabel = computed(() =>
  formatDateTime(selectedReport.value?.generated_at ?? summary.value?.generated_at),
)
const selectedReport = computed(() => {
  if (selectedReportId.value) {
    const archived = reportArchives.value.find((item) => item.id === selectedReportId.value)
    if (archived) {
      return archived
    }
  }
  return summary.value?.report ?? reportArchives.value[0] ?? null
})
const displayedReportId = computed(() => selectedReport.value?.id ?? null)
const activeSummaryMarkdown = computed(() => streamingMarkdown.value || selectedReport.value?.summary || '')
const reportAvailable = computed(() => Boolean(activeSummaryMarkdown.value))
const withoutReport = computed(() => Boolean(summary.value && !summary.value.report && !streamingMarkdown.value))
const streamingHint = computed(() => streamingStageMessage.value || t('analysisWorkbench.streamHint'))
const needsFallbackHint = computed(
  () => Boolean(selectedReport.value) && (selectedReport.value?.status ?? summary.value?.status) === 'partial',
)
const currentReportWebSearchStatus = computed(() =>
  useWebSearch.value
  && (!selectedReport.value?.web_search_status || selectedReport.value.web_search_status === 'disabled')
    ? translateWebSearchStatus('used')
    : translateWebSearchStatus(selectedReport.value?.web_search_status),
)
const reportRuntimeMeta = computed(() => {
  if (!selectedReport.value) {
    return []
  }
  return [
    selectedReport.value.prompt_version
      ? `Prompt ${selectedReport.value.prompt_version}`
      : null,
    selectedReport.value.model_name
      ? `模型 ${selectedReport.value.model_name}`
      : null,
    selectedReport.value.reasoning_effort
      ? `推理 ${selectedReport.value.reasoning_effort}`
      : null,
    typeof selectedReport.value.token_usage_input === 'number'
      ? `输入 Token ${selectedReport.value.token_usage_input}`
      : null,
    typeof selectedReport.value.token_usage_output === 'number'
      ? `输出 Token ${selectedReport.value.token_usage_output}`
      : null,
    selectedReport.value.failure_type
      ? `失败类型 ${selectedReport.value.failure_type}`
      : null,
  ].filter((item): item is string => Boolean(item))
})
const pipelineRoles = computed<AnalysisPipelineRoleResponse[]>(() => {
  const roles = selectedReport.value?.pipeline_roles ?? []
  return [...roles].sort((left, right) => (left.sort_order ?? 0) - (right.sort_order ?? 0))
})
const hasPipelineRoles = computed(() => pipelineRoles.value.length > 0)
const reportDecisionMeta = computed(() => {
  if (!selectedReport.value) {
    return []
  }
  return [
    selectedReport.value.selected_hypothesis
      ? `${t('analysisWorkbench.selectedHypothesis')} · ${selectedReport.value.selected_hypothesis}`
      : null,
    selectedReport.value.decision_confidence
      ? `${t('analysisWorkbench.decisionConfidence')} · ${translateConfidence(selectedReport.value.decision_confidence)}`
      : null,
    selectedReport.value.decision_reason_summary
      ? `${t('analysisWorkbench.decisionReason')} · ${selectedReport.value.decision_reason_summary}`
      : null,
  ].filter((item): item is string => Boolean(item))
})
const showWebSearchInheritedHint = computed(
  () => Boolean(watchlistItem.value) && webSearchInherited.value,
)

const sortedFactors = computed(() => {
  const factors = selectedReport.value?.factor_breakdown ?? []
  return [...factors].sort((left, right) => right.weight - left.weight)
})

const topFactor = computed(() => sortedFactors.value[0] ?? null)
const visibleFactors = computed(() =>
  showAllFactors.value ? sortedFactors.value : sortedFactors.value.slice(0, 3),
)
const hasMoreFactors = computed(() => sortedFactors.value.length > 3)
const highlightFactors = computed(() => sortedFactors.value.slice(0, 2))
const riskHighlights = computed(() => (selectedReport.value?.risk_points ?? []).slice(0, 3))
// 只有存在可切换的真实历史报告时才展示历史区，避免单报告场景浪费首屏空间。
const hasHistoricalReports = computed(() => reportArchives.value.length >= 2)
// 因子区与风险区共用第二行双列位，若其中一块无数据则让另一块自动占满整行。
const showFactorSpotlight = computed(() => highlightFactors.value.length > 0 || riskHighlights.value.length === 0)
const showRiskSpotlight = computed(() => riskHighlights.value.length > 0 || highlightFactors.value.length === 0)

const sortedEvents = computed(() => {
  const events = activeEvidenceEvents.value
  return [...events].sort((left, right) => {
    if (left.event_id === eventId.value && right.event_id !== eventId.value) {
      return -1
    }
    if (right.event_id === eventId.value && left.event_id !== eventId.value) {
      return 1
    }
    const correlationDelta =
      getCorrelationPercent(right.correlation_score) - getCorrelationPercent(left.correlation_score)
    if (correlationDelta !== 0) {
      return correlationDelta
    }

    const publishDelta =
      (parseTime(right.published_at)?.getTime() ?? 0) - (parseTime(left.published_at)?.getTime() ?? 0)
    if (publishDelta !== 0) {
      return publishDelta
    }

    return confidenceRank(right.confidence) - confidenceRank(left.confidence)
  })
})

const eventFilterOptions = computed(() => [
  { key: 'all' as const, label: t('analysisWorkbench.filters.all') },
  { key: 'high-related' as const, label: t('analysisWorkbench.filters.highRelated') },
  { key: 'policy' as const, label: t('analysisWorkbench.filters.policy') },
  { key: 'announcement' as const, label: t('analysisWorkbench.filters.announcement') },
  { key: 'news' as const, label: t('analysisWorkbench.filters.news') },
  { key: 'pending' as const, label: t('analysisWorkbench.filters.pending') },
])

const filteredEvents = computed(() => {
  return sortedEvents.value.filter((event) => {
    if (selectedEventFilter.value === 'all') {
      return true
    }
    if (selectedEventFilter.value === 'high-related') {
      return getCorrelationPercent(event.correlation_score) >= 70
    }
    if (selectedEventFilter.value === 'pending') {
      return event.link_status !== 'linked' || typeof event.correlation_score !== 'number'
    }
    return event.event_type === selectedEventFilter.value
  })
})

const visibleEvidenceMetricFlags = computed(() => ({
  windowReturn: hasUsefulMetricDifference(filteredEvents.value, (event) => event.window_return_pct),
  windowVolatility: hasUsefulMetricDifference(filteredEvents.value, (event) => event.window_volatility),
  abnormalVolume: hasUsefulMetricDifference(filteredEvents.value, (event) => event.abnormal_volume_ratio),
}))

const hasVisibleEvidenceMetricGroup = computed(() =>
  Object.values(visibleEvidenceMetricFlags.value).some((value) => value),
)

const hasVisibleEvidenceMetrics = (event: AnalysisEventResponse) => {
  const metricFlags = visibleEvidenceMetricFlags.value
  return (
    (metricFlags.windowReturn && typeof event.window_return_pct === 'number')
    || (metricFlags.windowVolatility && typeof event.window_volatility === 'number')
    || (metricFlags.abnormalVolume && typeof event.abnormal_volume_ratio === 'number')
  )
}

const emptyEventMessage = computed(() => {
  switch (selectedEventFilter.value) {
    case 'high-related':
      return t('analysisWorkbench.noEventsByFilter.highRelated')
    case 'policy':
      return t('analysisWorkbench.noEventsByFilter.policy')
    case 'announcement':
      return t('analysisWorkbench.noEventsByFilter.announcement')
    case 'news':
      return t('analysisWorkbench.noEventsByFilter.news')
    case 'pending':
      return t('analysisWorkbench.noEventsByFilter.pending')
    default:
      return t('analysisWorkbench.noEvents')
  }
})

const visibleEvents = computed(() =>
  showAllEvents.value ? filteredEvents.value : filteredEvents.value.slice(0, 4),
)
const hasMoreEvents = computed(() => filteredEvents.value.length > 4)

const structuredSourceItems = computed(() => selectedReport.value?.structured_sources ?? [])
const webSourceItems = computed(() => selectedReport.value?.web_sources ?? [])
const hasSourcesWorkspace = computed(
  () => structuredSourceItems.value.length > 0 || webSourceItems.value.length > 0 || reportRuntimeMeta.value.length > 0,
)

const hotNewsAnchorEvent = computed(() => {
  const matchedEvent =
    (eventId.value
      ? activeEvidenceEvents.value.find((item) => item.event_id === eventId.value)
      : null)
    ?? filteredEvents.value[0]
    ?? sortedEvents.value[0]

  if (!matchedEvent && !eventId.value && !eventTitle.value) {
    return null
  }

  return {
    eventId: matchedEvent?.event_id ?? eventId.value,
    eventTitle: matchedEvent?.title ?? eventTitle.value,
  }
})

const latestCloseLabel = computed(() => formatPrice(summary.value?.latest_snapshot?.close))
const latestChangeLabel = computed(() => formatPercent(summary.value?.latest_snapshot?.pct_chg))

const overviewItems = computed(() => [
  {
    key: 'close',
    label: t('analysisWorkbench.metricClose'),
    value: latestCloseLabel.value,
  },
  {
    key: 'change',
    label: t('analysisWorkbench.metricChange'),
    value: latestChangeLabel.value,
  },
  {
    key: 'events',
    label: t('analysisWorkbench.metricEvents'),
    value: String(activeEvidenceTotal.value),
  },
  {
    key: 'factor',
    label: t('analysisWorkbench.metricTopFactor'),
    value: topFactor.value
      ? `${topFactor.value.factor_label} · ${formatWeight(topFactor.value.weight)}`
      : t('analysisWorkbench.noFactors'),
  },
  {
    key: 'status',
    label: t('analysisWorkbench.metricStatus'),
    value: displayStatus.value,
  },
])

const overviewGridItems = computed(() =>
  overviewItems.value.map((item, index, items) => ({
    ...item,
    isWide: items.length % 2 === 1 && index === items.length - 1,
  })),
)

const decisionGlanceItems = computed(() => {
  const items = [
    selectedReport.value?.selected_hypothesis
      ? {
          key: 'hypothesis',
          label: t('analysisWorkbench.selectedHypothesis'),
          value: selectedReport.value.selected_hypothesis,
        }
      : null,
    selectedReport.value?.decision_confidence
      ? {
          key: 'confidence',
          label: t('analysisWorkbench.decisionConfidence'),
          value: translateConfidence(selectedReport.value.decision_confidence),
        }
      : null,
    selectedReport.value?.decision_reason_summary
      ? {
          key: 'reason',
          label: t('analysisWorkbench.decisionReason'),
          value: selectedReport.value.decision_reason_summary,
        }
      : null,
  ].filter(
    (
      item,
    ): item is {
      key: string
      label: string
      value: string
    } => Boolean(item),
  )

  return items.map((item, index) => ({
    ...item,
    isWide: items.length % 2 === 1 && index === items.length - 1,
  }))
})

const contextItems = computed(() =>
  [
    `${t('analysisWorkbench.contextSource')}: ${sourceLabel.value}`,
    topicContext.value
      ? `${t('analysisWorkbench.contextTopic')}: ${topicContext.value}`
      : null,
    eventTitle.value
      ? `${t('analysisWorkbench.contextEvent')}: ${eventTitle.value}`
      : eventId.value
        ? `${t('analysisWorkbench.contextEvent')}: ${eventId.value}`
        : null,
    summary.value?.instrument?.industry
      ? `${t('analysisWorkbench.contextIndustry')}: ${summary.value.instrument.industry}`
      : null,
  ].filter((item): item is string => Boolean(item)),
)

const sourceActionLabel = computed(() => {
  if (sourceKind.value === 'watchlist') {
    return t('analysisWorkbench.backToWatchlist')
  }
  if (sourceKind.value === 'hot_news') {
    return t('analysisWorkbench.backToHotTopic')
  }
  if (sourceKind.value === 'stock_detail') {
    return t('analysisWorkbench.backToStockDetail')
  }
  return t('analysisWorkbench.backToHome')
})

const watchlistButtonLabel = computed(() => {
  if (!authStore.accessToken) {
    return t('analysisWorkbench.watchlistLoginCompact')
  }
  return watchlistItem.value ? t('analysisWorkbench.watchlistRemove') : t('analysisWorkbench.watchlistAdd')
})

const loadSummary = async (requestVersion: number) => {
  const currentTsCode = tsCode.value
  const currentTopic = topicContext.value || null
  const currentEventId = eventId.value || null

  if (!currentTsCode) {
    if (!isLatestWorkbenchRequest(requestVersion)) {
      return
    }
    // 没有股票代码时立即清空摘要区，避免残留上一次的分析内容。
    summary.value = null
    errorMessage.value = ''
    loading.value = false
    selectedEventFilter.value = 'all'
    showAllFactors.value = false
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const payload = await analysisApi.getStockAnalysisSummary(currentTsCode, {
      topic: currentTopic,
      eventId: currentEventId,
    })
    if (!isLatestWorkbenchRequest(requestVersion)) {
      return
    }
    // 成功态只写入最新请求的结果，避免用户切换股票后被旧响应覆盖。
    summary.value = payload
    if (!selectedReportId.value && payload.report?.id) {
      selectedReportId.value = payload.report.id
    }
    selectedEventFilter.value = 'all'
    showAllFactors.value = false
  } catch {
    if (!isLatestWorkbenchRequest(requestVersion)) {
      return
    }
    errorMessage.value = t('analysisWorkbench.error')
    summary.value = null
  } finally {
    if (isLatestWorkbenchRequest(requestVersion)) {
      loading.value = false
    }
  }
}

const loadReports = async (requestVersion: number) => {
  const currentTsCode = tsCode.value
  const currentTopic = topicContext.value || null
  const currentEventId = eventId.value || null

  if (!currentTsCode) {
    if (isLatestWorkbenchRequest(requestVersion)) {
      // 空上下文时清空历史列表，确保页面状态与路由一致。
      reportArchives.value = []
    }
    return
  }
  try {
    const payload = await analysisApi.getStockAnalysisReports(currentTsCode, 10, {
      topic: currentTopic,
      eventId: currentEventId,
    })
    if (!isLatestWorkbenchRequest(requestVersion)) {
      return
    }
    // 仅同步当前页面上下文的历史报告，避免跨股票污染。
    reportArchives.value = payload.items
    if (!selectedReportId.value && payload.items[0]?.id) {
      selectedReportId.value = payload.items[0].id
    }
  } catch {
    if (isLatestWorkbenchRequest(requestVersion)) {
      reportArchives.value = []
    }
  }
}

const applyActiveEvidence = (events: AnalysisEventResponse[], total: number) => {
  activeEvidenceEvents.value = events
  activeEvidenceTotal.value = Math.max(total, events.length)
}

const resolveInlineEvidence = (report: AnalysisReportResponse | null) => {
  if (!report) {
    return null
  }

  if (report.evidence_events?.length) {
    return {
      event_count: report.evidence_event_count ?? report.evidence_events.length,
      events: report.evidence_events,
    } satisfies ReportEvidencePayload
  }

  const summaryReport = summary.value?.report
  if (summaryReport?.id && report.id === summaryReport.id) {
    return {
      event_count: summary.value?.event_count ?? summary.value?.events.length ?? 0,
      events: summary.value?.events ?? [],
    } satisfies ReportEvidencePayload
  }

  return null
}

const syncActiveEvidence = async () => {
  const currentReport = selectedReport.value
  const inlineEvidence = resolveInlineEvidence(currentReport)
  if (inlineEvidence) {
    applyActiveEvidence(inlineEvidence.events, inlineEvidence.event_count)
    return
  }

  if (!currentReport?.id) {
    const summaryEvents = summary.value?.events ?? []
    applyActiveEvidence(summaryEvents, summary.value?.event_count ?? summaryEvents.length)
    return
  }

  const cachedEvidence = reportEvidenceCache.value[currentReport.id]
  if (cachedEvidence) {
    applyActiveEvidence(cachedEvidence.events, cachedEvidence.event_count)
    return
  }

  const currentLoadToken = activeEvidenceLoadToken + 1
  activeEvidenceLoadToken = currentLoadToken
  // 关键流程：历史报告切换时先清空旧证据，避免上一份报告的证据在异步请求返回前残留。
  applyActiveEvidence([], currentReport.evidence_event_count ?? 0)
  try {
    const payload = await analysisApi.getAnalysisReportEvidence(currentReport.id)
    if (
      currentLoadToken !== activeEvidenceLoadToken
      || displayedReportId.value !== currentReport.id
    ) {
      return
    }
    reportEvidenceCache.value = {
      ...reportEvidenceCache.value,
      [currentReport.id]: payload,
    }
    applyActiveEvidence(payload.events, payload.event_count)
  } catch {
    if (
      currentLoadToken !== activeEvidenceLoadToken
      || displayedReportId.value !== currentReport.id
    ) {
      return
    }
    applyActiveEvidence([], currentReport.evidence_event_count ?? 0)
  }
}

const loadWatchlistState = async (requestVersion: number) => {
  const currentToken = authStore.accessToken
  const currentTsCode = tsCode.value
  if (!currentToken || !currentTsCode) {
    if (isLatestWorkbenchRequest(requestVersion)) {
      // 未登录或缺少股票代码时直接移除关注态。
      watchlistItem.value = null
    }
    return
  }
  try {
    const payload = await watchlistApi.getWatchlist(currentToken)
    // 关键流程：只允许最新页面上下文写回关注态，避免旧股票或旧登录态覆盖当前分析页。
    if (
      !isLatestWorkbenchRequest(requestVersion)
      || authStore.accessToken !== currentToken
      || tsCode.value !== currentTsCode
    ) {
      return
    }
    const matchedItem = payload.items.find((item) => item.ts_code === currentTsCode) ?? null
    watchlistItem.value = matchedItem

    // 关键流程：关注页中的联网增强是“自动分析默认值”，分析页只在首次进入该股票时继承一次。
    // 这样既能保持默认一致，又不会在用户手动切换后被异步刷新重新覆盖。
    if (webSearchSeededTsCode.value !== currentTsCode) {
      useWebSearch.value = Boolean(matchedItem?.web_search_enabled)
      webSearchInherited.value = Boolean(matchedItem)
      webSearchSeededTsCode.value = currentTsCode
    }
  } catch {
    if (
      isLatestWorkbenchRequest(requestVersion)
      && authStore.accessToken === currentToken
      && tsCode.value === currentTsCode
    ) {
      watchlistItem.value = null
    }
  }
}

const loadWorkbench = async () => {
  workbenchLoadVersion.value += 1
  const requestVersion = workbenchLoadVersion.value
  // 并发加载摘要、历史与关注态，用版本号保证回写一致性。
  await Promise.all([
    loadSummary(requestVersion),
    loadReports(requestVersion),
    loadWatchlistState(requestVersion),
  ])
}

const goToHotNews = async () => {
  await router.push('/news/hot')
}

const goToWatchlist = async () => {
  await router.push('/watchlist')
}

const goToStockDetail = async () => {
  if (!tsCode.value) {
    return
  }
  if (sourceKind.value === 'hot_news') {
    const query: Record<string, string> = {
      source: 'hot_news',
    }
    if (topicContext.value) {
      query.topic = topicContext.value
    }
    if (hotNewsAnchorEvent.value?.eventId) {
      query.event_id = hotNewsAnchorEvent.value.eventId
    }
    if (hotNewsAnchorEvent.value?.eventTitle) {
      query.event_title = hotNewsAnchorEvent.value.eventTitle
    }
    await router.push({
      path: `/stocks/${encodeURIComponent(tsCode.value)}`,
      query,
    })
    return
  }

  await router.push(`/stocks/${encodeURIComponent(tsCode.value)}`)
}

const goToSource = async () => {
  if (sourceKind.value === 'watchlist') {
    await router.push('/watchlist')
    return
  }

  if (sourceKind.value === 'hot_news') {
    const query: Record<string, string> = {}
    if (topicContext.value) {
      query.topic = topicContext.value
    }
    if (hotNewsAnchorEvent.value?.eventId) {
      query.event_id = hotNewsAnchorEvent.value.eventId
    }
    if (hotNewsAnchorEvent.value?.eventTitle) {
      query.event_title = hotNewsAnchorEvent.value.eventTitle
    }
    await router.push({
      path: '/news/hot',
      query,
    })
    return
  }

  if (sourceKind.value === 'stock_detail' && tsCode.value) {
    await router.push(`/stocks/${encodeURIComponent(tsCode.value)}`)
    return
  }

  await router.push('/')
}

const selectFilter = (filterKey: EventFilterKey) => {
  selectedEventFilter.value = filterKey
  showAllEvents.value = false
}

const selectReport = (reportId: string | null | undefined) => {
  if (!reportId) {
    return
  }
  selectedReportId.value = reportId
  streamingMarkdown.value = ''
  showAllFactors.value = false
  showAllEvents.value = false
  expandedRolePayloads.value = {}
}

const toggleRolePayload = (roleKey: string) => {
  expandedRolePayloads.value = {
    ...expandedRolePayloads.value,
    [roleKey]: !expandedRolePayloads.value[roleKey],
  }
}

const toggleWatchlist = async () => {
  if (!tsCode.value) {
    return
  }
  if (!authStore.accessToken) {
    // 未登录时引导去登录，并保留当前页作为回跳目标。
    await router.push({
      path: '/login',
      query: { redirect: route.fullPath },
    })
    return
  }

  watchlistLoading.value = true
  try {
    if (watchlistItem.value) {
      await watchlistApi.deleteWatchlistItem(authStore.accessToken, tsCode.value)
      watchlistItem.value = null
      webSearchInherited.value = false
    } else {
      watchlistItem.value = await watchlistApi.createWatchlistItem(authStore.accessToken, {
        ts_code: tsCode.value,
      })
    }
  } finally {
    watchlistLoading.value = false
  }
}

const updateUseWebSearch = (value: boolean) => {
  useWebSearch.value = value
  webSearchInherited.value = false
}

const scheduleSessionPoll = (sessionId: string, pollingToken: number) => {
  if (pollingToken !== activePollingToken) {
    return
  }
  sessionPollTimer = window.setTimeout(() => {
    void pollAnalysisSession(sessionId, pollingToken)
  }, 1000)
}

const pollAnalysisSession = async (sessionId: string, pollingToken: number) => {
  if (pollingToken !== activePollingToken) {
    return
  }

  try {
    const payload = await analysisApi.getAnalysisSessionStatus(sessionId)
    if (pollingToken !== activePollingToken) {
      return
    }

    if (payload.summary_preview) {
      streamingMarkdown.value = payload.summary_preview
    }
    streamingStageMessage.value = payload.stage_message || ''

    if (payload.heartbeat_at) {
      if (payload.heartbeat_at !== lastHeartbeatValue.value) {
        lastHeartbeatValue.value = payload.heartbeat_at
        lastHeartbeatObservedAt.value = Date.now()
      }
    }
    const heartbeatExpired =
      payload.status !== 'completed'
      && payload.status !== 'failed'
      && lastHeartbeatObservedAt.value !== null
      && Date.now() - lastHeartbeatObservedAt.value > 45_000

    if (payload.status === 'completed') {
      streaming.value = false
      stopStreaming()
      await loadWorkbench()
      return
    }

    if (payload.status === 'failed' || heartbeatExpired) {
      streaming.value = false
      errorMessage.value = heartbeatExpired
        ? '分析任务长时间未更新，请稍后重试'
        : String(payload.error_message || t('analysisWorkbench.error'))
      stopStreaming()
      return
    }

    scheduleSessionPoll(sessionId, pollingToken)
  } catch {
    if (pollingToken !== activePollingToken) {
      return
    }
    streaming.value = false
    errorMessage.value = t('analysisWorkbench.error')
    stopStreaming()
  }
}

const refreshAnalysis = async () => {
  if (!tsCode.value) {
    return
  }

  stopStreaming()
  streaming.value = true
  streamingMarkdown.value = ''
  streamingStageMessage.value = ''

  try {
    const session = await analysisApi.createAnalysisSession(tsCode.value, {
      topic: topicContext.value || null,
      event_id: eventId.value || null,
      force_refresh: true,
      use_web_search: useWebSearch.value,
      trigger_source: 'manual',
      analysis_mode: 'functional_multi_agent',
    })
    if (session.cached || !session.session_id) {
      // 缓存命中或未分配流式会话时，直接回拉最新数据即可。
      streaming.value = false
      await loadWorkbench()
      return
    }

    activePollingToken += 1
    const pollingToken = activePollingToken
    await pollAnalysisSession(session.session_id, pollingToken)
  } catch {
    streaming.value = false
    errorMessage.value = t('analysisWorkbench.error')
  }
}

const triggerReportDownload = (content: string, fileName: string, mimeType: string) => {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return
  }
  const normalizedContent = mimeType.includes('text/markdown') ? `\uFEFF${content}` : content
  const blob = new Blob([normalizedContent], { type: mimeType })
  const objectUrl = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = fileName
  try {
    document.body.appendChild(anchor)
  } catch {
    // 测试环境中的锚点桩对象不是原生节点时，允许跳过真实挂载。
  }
  anchor.click()
  try {
    document.body.removeChild(anchor)
  } catch {
    // 同上：测试桩对象可能无法作为真实节点移除。
  }
  window.setTimeout(() => {
    window.URL.revokeObjectURL(objectUrl)
  }, 0)
}

const exportSelectedReport = async (format: 'markdown' | 'html') => {
  if (!selectedReport.value?.id) {
    return
  }
  exportLoading.value = true
  try {
    const content = await analysisApi.exportReport(selectedReport.value.id, format)
    if (!content.trim()) {
      throw new Error('empty_export_content')
    }
    const suffix = format === 'html' ? 'html' : 'md'
    triggerReportDownload(
      content,
      `${tsCode.value || 'analysis-report'}-${selectedReport.value.id}.${suffix}`,
      format === 'html' ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8',
    )
  } catch {
    errorMessage.value = '导出报告失败，请稍后重试'
  } finally {
    exportLoading.value = false
  }
}

watch(
  [selectedReport, summary, reportArchives],
  () => {
    void syncActiveEvidence()
  },
  { immediate: true },
)

onMounted(() => {
  void loadWorkbench()
})

onBeforeUnmount(() => {
  stopStreaming()
})

watch(
  () => authStore.accessToken,
  (token) => {
    if (!token) {
      // 关键流程：登出后立即移除“已关注/继承默认值”状态，但保留用户手动切换过的本次分析开关。
      watchlistItem.value = null
      watchlistLoading.value = false
      webSearchInherited.value = false
      return
    }
    if (!tsCode.value) {
      return
    }
    // 重新登录后刷新关注态，确保按钮与后端一致。
    void loadWatchlistState(workbenchLoadVersion.value)
  },
)

watch(
  () => `${tsCode.value}|${topicContext.value}|${eventId.value}`,
  () => {
    stopStreaming()
    streaming.value = false
    analysisViewMode.value = 'events'
    selectedReportId.value = null
    streamingMarkdown.value = ''
    reportEvidenceCache.value = {}
    activeEvidenceEvents.value = []
    activeEvidenceTotal.value = 0
    activeEvidenceLoadToken += 1
    expandedRolePayloads.value = {}
    showAllEvents.value = false
    // 路由上下文变化时重置继承状态，避免旧股票影响新分析。
    useWebSearch.value = false
    webSearchInherited.value = false
    webSearchSeededTsCode.value = ''
    watchlistItem.value = null
    void loadWorkbench()
  },
)
</script>

<template>
  <section class="analysis-workbench">
    <el-card v-if="!hasTsCode" class="analysis-empty">
      <div class="analysis-empty__content">
        <p class="analysis-empty__title">{{ t('analysisWorkbench.emptyTitle') }}</p>
        <p class="analysis-empty__desc">{{ t('analysisWorkbench.emptyDesc') }}</p>
        <div class="analysis-empty__actions">
          <el-button plain @click="goToWatchlist">
            {{ t('analysisWorkbench.emptyWatchlistAction') }}
          </el-button>
          <el-button type="primary" @click="goToHotNews">
            {{ t('analysisWorkbench.emptyHotNewsAction') }}
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card v-else-if="errorMessage" class="analysis-error">
      <p class="analysis-error__title">{{ t('analysisWorkbench.errorTitle') }}</p>
      <p class="analysis-error__desc">{{ errorMessage }}</p>
      <div class="analysis-error__actions">
        <el-button type="primary" :loading="loading || streaming" @click="refreshAnalysis">
          {{ t('analysisWorkbench.refreshAction') }}
        </el-button>
        <el-button plain @click="goToSource">
          {{ sourceActionLabel }}
        </el-button>
      </div>
    </el-card>

    <template v-else>
      <div v-if="loading && !summary" class="analysis-loading">
        <el-card class="analysis-skeleton analysis-skeleton--hero">
          <el-skeleton :rows="4" animated />
        </el-card>
        <div class="analysis-loading__grid">
          <el-card class="analysis-skeleton">
            <el-skeleton :rows="6" animated />
          </el-card>
          <el-card class="analysis-skeleton">
            <el-skeleton :rows="7" animated />
          </el-card>
        </div>
      </div>

      <div v-else class="analysis-shell">
        <el-card class="analysis-hero" data-testid="analysis-research-header">
          <div class="analysis-hero__header">
            <div class="analysis-hero__headline">
              <p class="analysis-kicker">{{ t('analysisWorkbench.panelTitle') }}</p>
              <div class="analysis-hero__title-row">
                <div>
                  <h1 class="analysis-hero__title">{{ displayName }}</h1>
                  <p class="analysis-hero__code">{{ summary?.ts_code ?? tsCode }}</p>
                </div>
                <span class="analysis-status-pill" :data-status="summary?.status ?? 'pending'">
                  {{ displayStatus }}
                </span>
              </div>
              <p class="analysis-hero__generated">
                {{ t('analysisWorkbench.generatedAt') }}：{{ generatedAtLabel }}
              </p>
              <div class="analysis-hero__context">
                <span
                  v-for="item in contextItems"
                  :key="item"
                  class="analysis-context-chip"
                >
                  {{ item }}
                </span>
              </div>
            </div>

            <div class="analysis-hero__actions" data-testid="analysis-hero-toolbar">
              <div class="analysis-hero__controls" data-testid="analysis-hero-controls">
                <div class="analysis-switch">
                  <div class="analysis-switch__copy">
                    <span class="analysis-switch__label" data-testid="analysis-switch-label">
                      {{ t('analysisWorkbench.webSearchToggle') }}
                    </span>
                    <p v-if="showWebSearchInheritedHint" class="analysis-switch__hint">
                      {{ t('analysisWorkbench.webSearchInheritedHint') }}
                    </p>
                  </div>
                  <div class="analysis-switch__toggle" data-testid="analysis-switch-toggle">
                    <el-switch
                      :model-value="useWebSearch"
                      @update:model-value="updateUseWebSearch"
                    />
                  </div>
                </div>
              </div>

              <div
                class="analysis-hero__action-cluster"
                data-testid="analysis-hero-action-cluster"
              >
                <div
                  class="analysis-hero__action-rail"
                  data-testid="analysis-hero-action-rail"
                >
                  <div
                    class="analysis-hero__primary-actions"
                    data-testid="analysis-hero-primary-actions"
                  >
                    <el-button
                      class="analysis-action-btn analysis-action-btn--primary"
                      type="primary"
                      :loading="loading || streaming"
                      @click="refreshAnalysis"
                    >
                      {{ t('analysisWorkbench.refreshAction') }}
                    </el-button>
                    <el-button
                      class="analysis-action-btn analysis-action-btn--outline"
                      plain
                      :disabled="!hasTsCode"
                      @click="goToStockDetail"
                    >
                      {{ t('analysisWorkbench.viewStockDetailAction') }}
                    </el-button>
                  </div>

                  <div
                    class="analysis-hero__secondary-actions"
                    data-testid="analysis-hero-secondary-actions"
                  >
                    <el-button
                      class="analysis-action-btn analysis-action-btn--outline"
                      plain
                      :disabled="!selectedReport?.id"
                      :loading="exportLoading"
                      @click="exportSelectedReport('markdown')"
                    >
                      导出 Markdown
                    </el-button>
                    <el-button
                      class="analysis-action-btn analysis-action-btn--outline"
                      plain
                      :disabled="!selectedReport?.id"
                      :loading="exportLoading"
                      @click="exportSelectedReport('html')"
                    >
                      导出 HTML
                    </el-button>
                    <el-button
                      class="analysis-action-btn analysis-action-btn--outline"
                      plain
                      :loading="watchlistLoading"
                      @click="toggleWatchlist"
                    >
                      {{ watchlistButtonLabel }}
                    </el-button>
                    <el-button
                      class="analysis-action-btn analysis-action-btn--outline"
                      data-testid="analysis-source-action"
                      plain
                      @click="goToSource"
                    >
                      {{ sourceActionLabel }}
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="analysis-overview">
            <article
              v-for="item in overviewGridItems"
              :key="item.key"
              class="analysis-overview__item"
              :class="{ 'analysis-overview__item--wide': item.isWide }"
            >
              <span class="analysis-overview__label">{{ item.label }}</span>
              <strong class="analysis-overview__value">{{ item.value }}</strong>
            </article>
          </div>
        </el-card>

        <div class="analysis-content">
          <div class="analysis-main">
            <div class="analysis-decision-layout" data-testid="analysis-decision-deck">
              <el-card class="analysis-panel analysis-panel--summary" data-testid="analysis-summary-panel">
                <div class="analysis-panel__header">
                  <div>
                    <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.summaryTitle') }}</p>
                    <h2 class="analysis-panel__title">{{ t('analysisWorkbench.summarySubtitle') }}</h2>
                  </div>
                  <div class="analysis-panel__meta-stack">
                    <span class="analysis-panel__meta">
                      {{ t('analysisWorkbench.metricStatus') }} · {{ displayStatus }}
                    </span>
                    <span v-if="selectedReport" class="analysis-panel__meta">
                      {{ t('analysisWorkbench.webSearchStatusLabel') }} · {{ currentReportWebSearchStatus }}
                    </span>
                  </div>
                </div>

                <div v-if="decisionGlanceItems.length > 0" class="analysis-decision-glance">
                  <article
                    v-for="item in decisionGlanceItems"
                    :key="item.key"
                    class="analysis-decision-glance__item"
                    :class="{ 'analysis-decision-glance__item--wide': item.isWide }"
                  >
                    <span class="analysis-overview__label">{{ item.label }}</span>
                    <strong class="analysis-overview__value">{{ item.value }}</strong>
                  </article>
                </div>

                <template v-if="reportAvailable">
                  <p v-if="streaming" class="analysis-summary__hint">
                    {{ streamingHint }}
                  </p>
                  <p v-if="needsFallbackHint" class="analysis-summary__hint">
                    {{ t('analysisWorkbench.partialHint') }}
                  </p>
                  <p v-if="summary?.event_context_message" class="analysis-summary__hint">
                    {{ summary.event_context_message }}
                  </p>
                  <MarkdownContent :source="activeSummaryMarkdown" />

                  <div
                    v-if="structuredSourceItems.length > 0"
                    class="analysis-source-evidence"
                  >
                    <span class="analysis-source-evidence__label">
                      {{ t('analysisWorkbench.inputSourcesLabel') }}
                    </span>
                    <span
                      v-for="sourceItem in structuredSourceItems"
                      :key="`${sourceItem.provider}-${sourceItem.count}`"
                      class="analysis-token"
                    >
                      {{ `${formatStructuredSourceProvider(sourceItem.provider) ?? 'source'} × ${sourceItem.count ?? 0}` }}
                    </span>
                  </div>
                </template>

                <template v-else-if="withoutReport">
                  <p v-if="streaming" class="analysis-summary__hint">{{ streamingHint }}</p>
                  <p class="analysis-summary__pending-title">{{ t('analysisWorkbench.pendingTitle') }}</p>
                  <p class="analysis-summary__body">{{ t('analysisWorkbench.pendingDesc') }}</p>
                </template>

                <template v-else>
                  <p v-if="streaming" class="analysis-summary__hint">{{ streamingHint }}</p>
                  <p class="analysis-summary__body">{{ t('analysisWorkbench.pendingDesc') }}</p>
                </template>
              </el-card>

              <div class="analysis-decision-side" data-testid="analysis-spotlight-row">
                <el-card
                  v-if="showFactorSpotlight"
                  class="analysis-panel analysis-panel--spotlight"
                  :class="{ 'analysis-panel--wide': !showRiskSpotlight }"
                  data-testid="analysis-factor-spotlight"
                >
                  <div class="analysis-panel__header">
                    <div>
                      <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.factorHeading') }}</p>
                      <h2 class="analysis-panel__title">{{ t('analysisWorkbench.factorSubtitle') }}</h2>
                    </div>
                  </div>

                  <div v-if="highlightFactors.length > 0" class="analysis-factor-list analysis-factor-list--spotlight">
                    <article
                      v-for="factor in highlightFactors"
                      :key="factor.factor_key"
                      class="analysis-factor-card analysis-factor-card--compact"
                    >
                      <div class="analysis-factor-card__header">
                        <div>
                          <p class="analysis-factor-card__title">{{ factor.factor_label }}</p>
                          <p class="analysis-factor-card__reason">{{ factor.reason }}</p>
                        </div>
                        <div class="analysis-factor-card__meta">
                          <strong>{{ formatWeight(factor.weight) }}</strong>
                          <span>{{ translateSentiment(factor.direction) }}</span>
                        </div>
                      </div>

                      <div class="analysis-factor-card__bar">
                        <span :style="{ width: `${Math.max(8, factor.weight * 100)}%` }" />
                      </div>

                      <div class="analysis-factor-card__evidence">
                        <span
                          v-for="evidence in factor.evidence"
                          :key="evidence"
                          class="analysis-token"
                        >
                          {{ evidence }}
                        </span>
                      </div>
                    </article>
                  </div>
                  <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.noFactors') }}</p>
                </el-card>

                <el-card
                  v-if="showRiskSpotlight"
                  class="analysis-panel analysis-panel--spotlight"
                  :class="{ 'analysis-panel--wide': !showFactorSpotlight }"
                  data-testid="analysis-risk-spotlight"
                >
                  <div class="analysis-panel__header">
                    <div>
                      <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.riskHeading') }}</p>
                      <h2 class="analysis-panel__title">{{ t('analysisWorkbench.riskSubtitle') }}</h2>
                    </div>
                  </div>

                  <ul v-if="riskHighlights.length > 0" class="analysis-risk-list">
                    <li v-for="point in riskHighlights" :key="point">
                      {{ point }}
                    </li>
                  </ul>
                  <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.noRisks') }}</p>
                </el-card>
              </div>
            </div>

            <el-card class="analysis-panel analysis-panel--workspace" data-testid="analysis-evidence-workspace">
              <div class="analysis-panel__header">
                <div>
                  <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.workspaceTitle') }}</p>
                  <h2 class="analysis-panel__title">{{ t('analysisWorkbench.workspaceSubtitle') }}</h2>
                </div>
                <span class="analysis-panel__meta">
                  {{ filteredEvents.length }} / {{ activeEvidenceTotal }}
                </span>
              </div>

              <div class="analysis-view-toggle analysis-view-toggle--workspace">
                <button
                  type="button"
                  class="analysis-filter-chip"
                  data-testid="analysis-view-events"
                  :class="{ active: analysisViewMode === 'events' }"
                  @click="analysisViewMode = 'events'"
                >
                  {{ t('analysisWorkbench.eventsView') }}
                </button>
                <button
                  type="button"
                  class="analysis-filter-chip"
                  data-testid="analysis-view-factors"
                  :class="{ active: analysisViewMode === 'factors' }"
                  @click="analysisViewMode = 'factors'"
                >
                  {{ t('analysisWorkbench.factorsView') }}
                </button>
                <button
                  type="button"
                  class="analysis-filter-chip"
                  data-testid="analysis-view-pipeline"
                  :class="{ active: analysisViewMode === 'pipeline' }"
                  @click="analysisViewMode = 'pipeline'"
                >
                  {{ t('analysisWorkbench.pipelineView') }}
                </button>
                <button
                  type="button"
                  class="analysis-filter-chip"
                  data-testid="analysis-view-sources"
                  :class="{ active: analysisViewMode === 'sources' }"
                  @click="analysisViewMode = 'sources'"
                >
                  {{ t('analysisWorkbench.sourcesView') }}
                </button>
              </div>

          <template v-if="analysisViewMode === 'events'">
            <div class="analysis-filter-row">
              <button
                v-for="filterOption in eventFilterOptions"
                :key="filterOption.key"
                type="button"
                class="analysis-filter-chip"
                :class="{ active: selectedEventFilter === filterOption.key }"
                @click="selectFilter(filterOption.key)"
              >
                {{ filterOption.label }}
              </button>
            </div>

            <div v-if="visibleEvents.length > 0" class="analysis-event-list">
              <article
                v-for="event in visibleEvents"
                :key="event.event_id"
                class="analysis-event-card"
                :class="{ 'analysis-event-card--anchor': event.event_id === eventId }"
              >
                <div class="analysis-event-card__header">
                  <p data-testid="analysis-event-title" class="analysis-event-card__title">
                    {{ event.title }}
                  </p>
                  <span class="analysis-token analysis-token--confidence">
                    {{ translateConfidence(event.confidence) }}
                  </span>
                </div>

                <p class="analysis-event-card__meta">
                  {{ formatDateTime(event.published_at) }} ·
                  {{ event.source || t('analysisWorkbench.dataMissing') }}
                </p>

                <div class="analysis-event-card__tags">
                  <span v-if="event.macro_topic" class="analysis-token">
                    {{ event.macro_topic }}
                  </span>
                  <span class="analysis-token">
                    {{ event.event_type || t('analysisWorkbench.noEventType') }}
                  </span>
                  <span class="analysis-token">
                    {{ translateSentiment(event.sentiment_label) }}
                  </span>
                </div>

                <div v-if="hasCorrelationMetric(event.correlation_score)" class="analysis-event-card__score">
                  <div class="analysis-event-card__score-head">
                    <span>{{ t('analysisWorkbench.correlation') }}</span>
                    <strong>{{ getCorrelationPercent(event.correlation_score) }}/100</strong>
                  </div>
                  <div class="analysis-score-bar">
                    <span :style="{ width: `${getCorrelationPercent(event.correlation_score)}%` }" />
                  </div>
                </div>

                <div
                  v-if="hasVisibleEvidenceMetricGroup && hasVisibleEvidenceMetrics(event)"
                  class="analysis-event-card__stats"
                >
                  <div v-if="visibleEvidenceMetricFlags.windowReturn && typeof event.window_return_pct === 'number'">
                    <span>{{ t('analysisWorkbench.windowReturn') }}</span>
                    <strong>{{ formatPercent(event.window_return_pct) }}</strong>
                  </div>
                  <div
                    v-if="visibleEvidenceMetricFlags.windowVolatility && typeof event.window_volatility === 'number'"
                  >
                    <span>{{ t('analysisWorkbench.windowVolatility') }}</span>
                    <strong>{{ formatMetricNumber(event.window_volatility) }}</strong>
                  </div>
                  <div
                    v-if="visibleEvidenceMetricFlags.abnormalVolume && typeof event.abnormal_volume_ratio === 'number'"
                  >
                    <span>{{ t('analysisWorkbench.abnormalVolume') }}</span>
                    <strong>{{ formatMetricNumber(event.abnormal_volume_ratio) }}</strong>
                  </div>
                </div>
              </article>
            </div>
            <p v-else class="analysis-empty-note">{{ emptyEventMessage }}</p>

            <div v-if="hasMoreEvents || showAllEvents" class="analysis-factor__actions">
              <el-button text @click="showAllEvents = !showAllEvents">
                {{ showAllEvents ? t('analysisWorkbench.showLessEvents') : t('analysisWorkbench.showMoreEvents') }}
              </el-button>
            </div>
          </template>

          <template v-else-if="analysisViewMode === 'factors'">
            <div v-if="visibleFactors.length > 0" class="analysis-factor-list analysis-factor-list--workspace">
              <article
                v-for="factor in visibleFactors"
                :key="factor.factor_key"
                class="analysis-factor-card"
              >
                <div class="analysis-factor-card__header">
                  <div>
                    <p class="analysis-factor-card__title">{{ factor.factor_label }}</p>
                    <p class="analysis-factor-card__reason">{{ factor.reason }}</p>
                  </div>
                  <div class="analysis-factor-card__meta">
                    <strong>{{ formatWeight(factor.weight) }}</strong>
                    <span>{{ translateSentiment(factor.direction) }}</span>
                  </div>
                </div>

                <div class="analysis-factor-card__bar">
                  <span :style="{ width: `${Math.max(8, factor.weight * 100)}%` }" />
                </div>

                <div class="analysis-factor-card__evidence">
                  <span
                    v-for="evidence in factor.evidence"
                    :key="evidence"
                    class="analysis-token"
                  >
                    {{ evidence }}
                  </span>
                </div>
              </article>
            </div>
            <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.noFactors') }}</p>

            <div v-if="hasMoreFactors" class="analysis-factor__actions">
              <el-button text @click="showAllFactors = !showAllFactors">
                {{ showAllFactors ? t('analysisWorkbench.collapseFactors') : t('analysisWorkbench.expandFactors') }}
              </el-button>
            </div>
          </template>

          <template v-else-if="analysisViewMode === 'pipeline'">
            <div v-if="hasPipelineRoles" class="analysis-pipeline">
              <div class="analysis-pipeline__summary">
                <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.pipelineTitle') }}</p>
                <p class="analysis-summary__hint">{{ t('analysisWorkbench.pipelineSubtitle') }}</p>
                <div
                  v-if="reportDecisionMeta.length > 0"
                  class="analysis-runtime-meta"
                >
                  <span
                    v-for="metaItem in reportDecisionMeta"
                    :key="metaItem"
                    class="analysis-token"
                  >
                    {{ metaItem }}
                  </span>
                </div>
              </div>
              <div class="analysis-pipeline__roles">
                <article
                  v-for="role in pipelineRoles"
                  :key="role.role_key"
                  class="analysis-pipeline-card"
                >
                  <div class="analysis-pipeline-card__header">
                    <div>
                      <strong>{{ role.role_label }}</strong>
                      <p v-if="role.summary" class="analysis-factor-card__reason">{{ role.summary }}</p>
                    </div>
                    <span class="analysis-token">
                      {{ translateRoleStatus(role.status) }}
                    </span>
                  </div>
                  <div class="analysis-pipeline-card__meta">
                    <span v-if="role.prompt_version" class="analysis-token">{{ role.prompt_version }}</span>
                    <span v-if="role.model_name" class="analysis-token">{{ role.model_name }}</span>
                    <span class="analysis-token">
                      {{ t('analysisWorkbench.roleWebSearch') }} · {{ translateWebSearchStatus(role.web_search_status) }}
                    </span>
                  </div>
                  <div v-if="role.output_payload && Object.keys(role.output_payload).length > 0" class="analysis-pipeline-card__body">
                    <button
                      type="button"
                      class="analysis-inline-toggle"
                      @click="toggleRolePayload(role.role_key)"
                    >
                      {{ expandedRolePayloads[role.role_key] ? t('analysisWorkbench.rawOutputHide') : t('analysisWorkbench.rawOutputToggle') }}
                    </button>
                    <pre
                      v-if="expandedRolePayloads[role.role_key]"
                      class="analysis-pipeline-card__payload"
                    >{{ JSON.stringify(role.output_payload, null, 2) }}</pre>
                  </div>
                </article>
              </div>
            </div>
            <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.pipelineEmpty') }}</p>
          </template>

          <template v-else>
            <div v-if="hasSourcesWorkspace" class="analysis-sources-workspace">
              <section v-if="structuredSourceItems.length > 0" class="analysis-sources-section">
                <p class="analysis-sources-section__title">{{ t('analysisWorkbench.inputSourcesLabel') }}</p>
                <div class="analysis-source-evidence">
                  <span
                    v-for="sourceItem in structuredSourceItems"
                    :key="`${sourceItem.provider}-${sourceItem.count}`"
                    class="analysis-token"
                  >
                    {{ `${formatStructuredSourceProvider(sourceItem.provider) ?? 'source'} × ${sourceItem.count ?? 0}` }}
                  </span>
                </div>
              </section>

              <section v-if="reportRuntimeMeta.length > 0" class="analysis-sources-section">
                <p class="analysis-sources-section__title">{{ t('analysisWorkbench.reportMetaTitle') }}</p>
                <div class="analysis-runtime-meta">
                  <span
                    v-for="metaItem in reportRuntimeMeta"
                    :key="metaItem"
                    class="analysis-token"
                  >
                    {{ metaItem }}
                  </span>
                </div>
              </section>

              <section v-if="webSourceItems.length > 0" class="analysis-sources-section">
                <p class="analysis-sources-section__title">{{ t('analysisWorkbench.sourcesView') }}</p>
                <div class="analysis-web-source-list">
                  <a
                    v-for="webSource in webSourceItems"
                    :key="`${webSource.url ?? webSource.title}-${webSource.published_at ?? ''}`"
                    class="analysis-web-source-item"
                    :href="webSource.url"
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    <strong>{{ webSource.title ?? webSource.url }}</strong>
                    <span>
                      {{ webSource.source || webSource.domain || t('analysisWorkbench.dataMissing') }}
                      ·
                      {{ webSource.published_at ? formatDateTime(webSource.published_at) : t('analysisWorkbench.webSourceMissingTime') }}
                    </span>
                    <span v-if="webSource.domain">{{ webSource.domain }}</span>
                    <span class="analysis-token">
                      {{ translateWebSourceMetadataStatus(webSource.metadata_status) }}
                    </span>
                    <span v-if="webSource.snippet">{{ webSource.snippet }}</span>
                  </a>
                </div>
              </section>
            </div>
            <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.sourcesEmpty') }}</p>
          </template>
            </el-card>

            <section
              v-if="hasHistoricalReports"
              class="analysis-history-section"
              data-testid="analysis-history-section"
            >
              <el-card class="analysis-panel">
                <div class="analysis-panel__header">
                  <div>
                    <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.historyTitle') }}</p>
                    <h2 class="analysis-panel__title">{{ t('analysisWorkbench.historyTitle') }}</h2>
                  </div>
                </div>

                <div v-if="selectedReport" class="analysis-history-spotlight">
                  <span class="analysis-overview__label">{{ t('analysisWorkbench.generatedAt') }}</span>
                  <strong class="analysis-overview__value">{{ formatDateTime(selectedReport.generated_at) }}</strong>
                  <p class="analysis-history-spotlight__meta">
                    {{ translateTriggerSource(selectedReport.trigger_source) }} · {{ displayStatus }}
                  </p>
                </div>

                <div class="analysis-history-list">
                  <button
                    v-for="reportItem in reportArchives"
                    :key="reportItem.id ?? reportItem.generated_at"
                    type="button"
                    class="analysis-history-item"
                    :class="{ active: selectedReportId === reportItem.id }"
                    @click="selectReport(reportItem.id)"
                  >
                    <strong>{{ formatDateTime(reportItem.generated_at) }}</strong>
                    <span>{{ translateTriggerSource(reportItem.trigger_source) }}</span>
                  </button>
                </div>
              </el-card>
            </section>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.analysis-workbench {
  display: grid;
  gap: 1rem;
}

.analysis-empty,
.analysis-error,
.analysis-skeleton,
.analysis-hero,
.analysis-panel {
  border-radius: 18px;
  border: 1px solid rgba(123, 197, 255, 0.12);
  background: var(--terminal-card-strong-bg);
  box-shadow: var(--terminal-shadow);
}

.analysis-empty,
.analysis-error {
  padding: 1.4rem;
}

.analysis-empty__content,
.analysis-error__actions {
  display: grid;
  gap: 0.8rem;
}

.analysis-empty__title,
.analysis-error__title {
  margin: 0;
  font-size: 1.28rem;
  font-weight: 600;
  color: var(--terminal-text);
}

.analysis-panel__meta,
.analysis-hero__generated,
.analysis-hero__code,
.analysis-event-card__stats span,
.analysis-overview__label {
  color: var(--terminal-text-secondary);
}

.analysis-empty__desc,
.analysis-error__desc,
.analysis-empty-note,
.analysis-factor-card__reason,
.analysis-summary__body,
.analysis-web-source-item {
  color: var(--terminal-text-body);
}

.analysis-empty__actions,
.analysis-error__actions {
  display: flex;
  gap: 0.7rem;
  flex-wrap: wrap;
}

.analysis-panel__meta-stack {
  display: grid;
  justify-items: end;
  gap: 0.2rem;
}

.analysis-loading {
  display: grid;
  gap: 1rem;
}

.analysis-loading__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.95fr);
  gap: 1rem;
}

.analysis-shell {
  display: grid;
  gap: 1rem;
}

.analysis-kicker,
.analysis-panel__eyebrow,
.analysis-overview__label,
.analysis-context-chip,
.analysis-token {
  font-family: 'IBM Plex Mono', monospace;
}

.analysis-kicker,
.analysis-panel__eyebrow {
  margin: 0 0 0.32rem;
  font-size: 0.76rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--terminal-primary);
}

.analysis-hero {
  padding: 1.2rem;
  overflow: hidden;
  background: var(--terminal-hero-bg);
}

.analysis-hero__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.analysis-hero__headline {
  display: grid;
  gap: 0.72rem;
  min-width: 0;
}

.analysis-hero__title-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.analysis-hero__title {
  margin: 0;
  font-size: clamp(1.62rem, 2.8vw, 2.3rem);
  color: var(--terminal-text);
}

.analysis-hero__code,
.analysis-hero__generated {
  margin: 0;
  font-size: 0.88rem;
}

.analysis-status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2rem;
  padding: 0.38rem 0.8rem;
  border-radius: 999px;
  border: 1px solid rgba(123, 197, 255, 0.18);
  background: color-mix(in srgb, var(--terminal-panel) 92%, var(--terminal-surface) 8%);
  color: var(--terminal-text);
  white-space: nowrap;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--terminal-primary) 10%, transparent);
}

.analysis-status-pill[data-status='ready'] {
  color: color-mix(in srgb, var(--terminal-success) 84%, var(--terminal-text-primary) 16%);
  border-color: color-mix(in srgb, var(--terminal-success) 34%, transparent);
  background: color-mix(in srgb, var(--terminal-success) 10%, var(--terminal-panel) 90%);
}

.analysis-status-pill[data-status='partial'] {
  color: color-mix(in srgb, var(--terminal-warning) 84%, var(--terminal-text-primary) 16%);
  border-color: color-mix(in srgb, var(--terminal-warning) 32%, transparent);
  background: color-mix(in srgb, var(--terminal-warning) 10%, var(--terminal-panel) 90%);
}

.analysis-status-pill[data-status='pending'] {
  color: color-mix(in srgb, var(--terminal-primary) 82%, var(--terminal-text-primary) 18%);
  border-color: color-mix(in srgb, var(--terminal-primary) 30%, transparent);
  background: color-mix(in srgb, var(--terminal-primary) 10%, var(--terminal-panel) 90%);
}

.analysis-hero__context {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.analysis-context-chip,
.analysis-token {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  border: 1px solid rgba(123, 197, 255, 0.16);
  background: var(--terminal-chip-bg);
  color: var(--terminal-primary);
  font-size: 0.74rem;
}

.analysis-hero__actions {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
  gap: 1rem;
  align-items: stretch;
}

.analysis-hero__controls {
  display: grid;
  gap: 0.6rem;
  align-content: center;
  padding: 0.9rem 1rem;
  min-width: 0;
  border: 1px solid rgba(123, 197, 255, 0.12);
  border-radius: 18px;
  background: color-mix(in srgb, var(--terminal-panel) 92%, var(--terminal-surface) 8%);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--terminal-primary) 5%, transparent);
}

.analysis-hero__action-cluster {
  display: flex;
  align-items: stretch;
  justify-content: flex-end;
  padding: 0.55rem;
  min-width: 0;
  border: 1px solid rgba(123, 197, 255, 0.1);
  border-radius: 18px;
  background: color-mix(in srgb, var(--terminal-panel) 92%, var(--terminal-surface) 8%);
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--terminal-primary) 4%, transparent),
    0 12px 32px color-mix(in srgb, var(--terminal-primary) 8%, transparent);
}

.analysis-hero__action-rail {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem;
  width: 100%;
  min-width: 0;
  align-items: stretch;
}

.analysis-hero__action-rail .el-button + .el-button {
  margin-left: 0;
}

.analysis-hero__primary-actions,
.analysis-hero__secondary-actions {
  display: contents;
}

.analysis-switch {
  display: grid;
  width: 100%;
  min-width: 0;
  gap: 0.7rem;
  color: var(--terminal-text-body);
}

.analysis-switch__copy {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
}

.analysis-switch__label {
  min-width: 0;
  display: block;
  font-weight: 600;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.analysis-switch__toggle {
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.analysis-switch__toggle :deep(.el-switch) {
  flex: 0 0 auto;
  padding: 0.2rem 0;
}

.analysis-switch__hint {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.55;
  color: var(--terminal-text-secondary);
}

.analysis-action-btn {
  min-width: 0;
  width: 100%;
  min-height: 2.75rem;
  box-sizing: border-box;
  border-radius: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.analysis-action-btn--primary {
  box-shadow: 0 10px 24px color-mix(in srgb, var(--terminal-primary) 24%, transparent);
}

.analysis-action-btn--outline.el-button.is-plain {
  border-color: rgba(123, 197, 255, 0.18);
  background: var(--terminal-outline-bg);
  color: var(--terminal-text-body);
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.05);
}

.analysis-action-btn--outline.el-button.is-plain:hover,
.analysis-action-btn--outline.el-button.is-plain:focus-visible {
  border-color: rgba(123, 197, 255, 0.34);
  background: var(--terminal-outline-hover-bg);
  color: var(--terminal-text-primary);
}

.analysis-action-btn--outline.el-button.is-plain:active {
  border-color: rgba(87, 184, 255, 0.42);
  background: var(--terminal-outline-active-bg);
}

.analysis-action-btn--outline.el-button.is-disabled,
.analysis-action-btn--outline.el-button.is-plain.is-disabled {
  border-color: rgba(123, 197, 255, 0.12);
  background: var(--terminal-outline-disabled-bg);
  color: var(--terminal-outline-disabled-text);
}

.analysis-overview {
  margin-top: 1rem;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.analysis-overview__item {
  display: grid;
  gap: 0.36rem;
  padding: 0.78rem 0.85rem;
  border-radius: 14px;
  border: 1px solid rgba(123, 197, 255, 0.08);
  background: color-mix(in srgb, var(--terminal-panel) 92%, var(--terminal-surface) 8%);
}

.analysis-overview__item--wide {
  grid-column: 1 / -1;
}

.analysis-decision-glance {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin-bottom: 0.95rem;
}

.analysis-decision-glance__item {
  display: grid;
  gap: 0.36rem;
  padding: 0.9rem 0.95rem;
  border-radius: 16px;
  border: 1px solid rgba(123, 197, 255, 0.1);
  background: color-mix(in srgb, var(--terminal-panel) 94%, var(--terminal-surface) 6%);
}

.analysis-decision-glance__item--wide {
  grid-column: 1 / -1;
}

.analysis-view-toggle {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-bottom: 0.9rem;
}

.analysis-view-toggle--workspace {
  padding-bottom: 0.15rem;
  border-bottom: 1px solid rgba(123, 197, 255, 0.08);
}

.analysis-pipeline {
  display: grid;
  gap: 1rem;
}

.analysis-pipeline__roles {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem;
}

.analysis-pipeline-card {
  display: grid;
  gap: 0.75rem;
  padding: 0.95rem 1rem;
  border-radius: 16px;
  border: 1px solid rgba(123, 197, 255, 0.12);
  background: color-mix(in srgb, var(--terminal-panel) 94%, var(--terminal-surface) 6%);
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.04);
}

.analysis-pipeline-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.8rem;
}

.analysis-pipeline-card__meta {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.analysis-pipeline-card__body {
  display: grid;
  gap: 0.45rem;
}

.analysis-inline-toggle {
  justify-self: flex-start;
  padding: 0.4rem 0.7rem;
  border-radius: 999px;
  border: 1px solid rgba(123, 197, 255, 0.16);
  background: var(--terminal-chip-bg);
  color: var(--terminal-primary);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
  cursor: pointer;
  transition: 0.2s ease;
}

.analysis-inline-toggle:hover,
.analysis-inline-toggle:focus-visible {
  border-color: rgba(123, 197, 255, 0.3);
  background: var(--terminal-chip-hover-bg);
  color: var(--terminal-text-primary);
}

.analysis-pipeline-card__payload {
  margin: 0;
  padding: 0.8rem 0.9rem;
  overflow-x: auto;
  border-radius: 12px;
  border: 1px solid rgba(123, 197, 255, 0.1);
  background: var(--terminal-code-bg);
  color: var(--terminal-code-text);
  font-size: 0.78rem;
  line-height: 1.55;
  font-family: 'IBM Plex Mono', monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

.analysis-overview__value {
  color: var(--terminal-text-primary);
  font-size: 1rem;
  line-height: 1.35;
}

.analysis-content {
  display: grid;
  gap: 1.1rem;
}

.analysis-main,
.analysis-history-section {
  display: grid;
  gap: 1rem;
}

.analysis-decision-layout {
  display: grid;
  gap: 1rem;
}

.analysis-decision-side {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.analysis-panel--wide {
  grid-column: 1 / -1;
}

.analysis-panel {
  padding: 1rem;
  overflow: hidden;
}

.analysis-panel--summary,
.analysis-panel--workspace,
.analysis-panel--spotlight {
  position: relative;
  background: var(--terminal-card-muted-bg);
}

.analysis-panel--summary {
  min-height: 100%;
}

.analysis-panel--workspace {
  border-color: rgba(123, 197, 255, 0.18);
  box-shadow:
    inset 0 0 0 1px rgba(123, 197, 255, 0.04),
    0 18px 40px color-mix(in srgb, var(--terminal-primary) 10%, transparent);
}

.analysis-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 0.9rem;
}

.analysis-panel__title {
  margin: 0;
  color: var(--terminal-text);
  font-size: 1.05rem;
}

.analysis-summary__hint {
  margin: 0 0 0.8rem;
  padding: 0.7rem 0.8rem;
  border-radius: 12px;
  border: 1px solid rgba(247, 181, 0, 0.18);
  background: color-mix(in srgb, var(--terminal-warning) 10%, var(--terminal-panel) 90%);
  color: color-mix(in srgb, var(--terminal-warning) 84%, var(--terminal-text) 16%);
}

.analysis-source-evidence {
  margin-bottom: 0.8rem;
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.analysis-source-evidence__label {
  color: var(--terminal-text-body);
  font-size: 0.82rem;
}

.analysis-runtime-meta {
  margin-bottom: 0.8rem;
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.analysis-sources-workspace {
  display: grid;
  gap: 1rem;
}

.analysis-sources-section {
  display: grid;
  gap: 0.6rem;
  padding: 0.85rem 0.9rem;
  border-radius: 16px;
  border: 1px solid rgba(123, 197, 255, 0.1);
  background: color-mix(in srgb, var(--terminal-panel) 92%, var(--terminal-surface) 8%);
}

.analysis-sources-section__title {
  margin: 0;
  color: var(--terminal-text);
  font-size: 0.9rem;
  font-weight: 600;
}

.analysis-web-source-list {
  margin-bottom: 0.8rem;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem;
}

.analysis-web-source-item {
  display: grid;
  gap: 0.2rem;
  padding: 0.75rem 0.85rem;
  border-radius: 12px;
  border: 1px solid rgba(123, 197, 255, 0.14);
  background: color-mix(in srgb, var(--terminal-panel) 94%, var(--terminal-surface) 6%);
  color: color-mix(in srgb, var(--terminal-text) 82%, var(--terminal-muted) 18%);
  text-decoration: none;
}

.analysis-web-source-item strong {
  color: var(--terminal-text);
}

.analysis-web-source-item span {
  color: var(--terminal-text-body);
}

.analysis-summary__body {
  margin: 0;
  line-height: 1.8;
  font-size: 0.98rem;
}

.analysis-summary__pending-title {
  margin: 0 0 0.4rem;
  color: var(--terminal-text);
  font-weight: 600;
}

.analysis-factor-list,
.analysis-history-list {
  display: grid;
  gap: 0.75rem;
}

.analysis-factor-list--workspace {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.analysis-event-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.analysis-history-item,
.analysis-factor-card,
.analysis-event-card {
  border-radius: 14px;
  border: 1px solid rgba(123, 197, 255, 0.08);
  background: color-mix(in srgb, var(--terminal-panel) 94%, var(--terminal-surface) 6%);
  padding: 0.82rem 0.88rem;
}

.analysis-factor-card--compact {
  padding: 0.88rem;
}

.analysis-event-card--anchor {
  border-color: rgba(123, 197, 255, 0.32);
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.08);
}

.analysis-history-item {
  display: grid;
  gap: 0.24rem;
  text-align: left;
  color: var(--terminal-text);
  cursor: pointer;
}

.analysis-history-item span {
  color: var(--terminal-text-body);
}

.analysis-history-item.active {
  border-color: rgba(123, 197, 255, 0.32);
  background: color-mix(in srgb, var(--terminal-primary) 14%, var(--terminal-panel) 86%);
}

.analysis-history-spotlight {
  display: grid;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
  padding: 0.85rem 0.9rem;
  border-radius: 14px;
  border: 1px solid rgba(123, 197, 255, 0.1);
  background: color-mix(in srgb, var(--terminal-panel) 94%, var(--terminal-surface) 6%);
}

.analysis-history-spotlight__meta {
  margin: 0;
  color: var(--terminal-text-body);
  font-size: 0.82rem;
}

.analysis-factor-card__header,
.analysis-event-card__header,
.analysis-event-card__score-head {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: flex-start;
}

.analysis-factor-card__title,
.analysis-event-card__title {
  margin: 0;
  color: var(--terminal-text);
  font-weight: 600;
}

.analysis-factor-card__reason,
.analysis-event-card__meta {
  margin: 0.25rem 0 0;
  font-size: 0.84rem;
  color: var(--terminal-text-body);
}

.analysis-factor-card__meta {
  display: grid;
  justify-items: end;
  gap: 0.2rem;
  color: var(--terminal-text-secondary);
  text-align: right;
}

.analysis-factor-card__bar,
.analysis-score-bar {
  margin-top: 0.78rem;
  height: 0.48rem;
  border-radius: 999px;
  background: var(--terminal-progress-track);
  overflow: hidden;
}

.analysis-factor-card__bar span,
.analysis-score-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--terminal-progress-fill);
}

.analysis-factor-card__evidence,
.analysis-event-card__tags {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  margin-top: 0.72rem;
}

.analysis-factor__actions {
  margin-top: 0.55rem;
  display: flex;
  justify-content: flex-end;
}

.analysis-filter-row {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  margin-bottom: 0.85rem;
}

.analysis-filter-chip {
  border: 1px solid rgba(123, 197, 255, 0.12);
  border-radius: 999px;
  padding: 0.32rem 0.68rem;
  background: var(--terminal-chip-bg);
  color: var(--terminal-text-body);
  cursor: pointer;
  transition: 0.2s ease;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
}

.analysis-filter-chip:hover,
.analysis-filter-chip:focus-visible {
  border-color: rgba(123, 197, 255, 0.24);
  background: var(--terminal-chip-hover-bg);
  color: var(--terminal-text-primary);
}

.analysis-filter-chip.active {
  background: var(--terminal-chip-active-bg);
  border-color: rgba(123, 197, 255, 0.3);
  color: var(--terminal-text-primary);
}

.analysis-event-card__score {
  margin-top: 0.75rem;
}

.analysis-event-card__stats {
  margin-top: 0.78rem;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.6rem;
}

.analysis-event-card__stats div {
  display: grid;
  gap: 0.24rem;
}

.analysis-event-card__stats strong,
.analysis-event-card__score-head strong {
  color: var(--terminal-text-primary);
}

.analysis-risk-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.65rem;
}

.analysis-risk-list li {
  border-left: 2px solid rgba(247, 181, 0, 0.72);
  padding-left: 0.75rem;
  color: var(--terminal-text-body);
  line-height: 1.6;
}

.analysis-token--confidence {
  color: var(--terminal-text-primary);
}

@media (max-width: 1040px) {
  .analysis-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .analysis-decision-side {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .analysis-hero {
    padding: 1rem;
  }

  .analysis-hero__header,
  .analysis-hero__title-row,
  .analysis-panel__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .analysis-empty__actions,
  .analysis-error__actions {
    width: 100%;
  }

  .analysis-hero__actions {
    grid-template-columns: 1fr;
  }

  .analysis-hero__action-cluster {
    width: 100%;
  }

  .analysis-hero__primary-actions,
  .analysis-hero__secondary-actions {
    display: contents;
  }

  .analysis-action-btn {
    width: 100%;
  }

  .analysis-overview {
    grid-template-columns: 1fr;
  }

  .analysis-decision-glance {
    grid-template-columns: 1fr;
  }

  .analysis-decision-side,
  .analysis-event-list,
  .analysis-factor-list--workspace,
  .analysis-pipeline__roles {
    grid-template-columns: 1fr;
  }

  .analysis-web-source-list {
    grid-template-columns: 1fr;
  }

  .analysis-event-card__stats {
    grid-template-columns: 1fr;
  }

  .analysis-loading__grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .analysis-hero__controls,
  .analysis-hero__action-cluster {
    padding: 0.85rem;
  }

  .analysis-hero__primary-actions,
  .analysis-hero__secondary-actions {
    display: contents;
  }

  .analysis-hero__action-rail {
    grid-template-columns: 1fr;
  }

  .analysis-action-btn--primary {
    box-shadow: 0 10px 24px rgba(64, 158, 255, 0.2);
  }
}
</style>
