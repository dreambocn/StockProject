<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import MarkdownContent from '../components/MarkdownContent.vue'
import {
  analysisApi,
  type AnalysisReportResponse,
  type StockAnalysisSummaryResponse,
} from '../api/analysis'
import { watchlistApi, type WatchlistItemResponse } from '../api/watchlist'
import { useAuthStore } from '../stores/auth'

type EventFilterKey = 'all' | 'high-related' | 'policy' | 'announcement' | 'news' | 'pending'
type SourceKind = 'hot_news' | 'stock_detail' | 'direct'

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
const selectedReportId = ref<string | null>(null)
const streamingMarkdown = ref('')
const streaming = ref(false)
const useWebSearch = ref(false)
const webSearchInherited = ref(false)
const webSearchSeededTsCode = ref('')
const watchlistLoading = ref(false)
const watchlistItem = ref<WatchlistItemResponse | null>(null)

let stopSessionStream: (() => void) | null = null

const stopStreaming = () => {
  stopSessionStream?.()
  stopSessionStream = null
}

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
  formatDateTime(summary.value?.report?.generated_at ?? summary.value?.generated_at),
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
const activeSummaryMarkdown = computed(() => streamingMarkdown.value || selectedReport.value?.summary || '')
const reportAvailable = computed(() => Boolean(activeSummaryMarkdown.value))
const withoutReport = computed(() => Boolean(summary.value && !summary.value.report && !streamingMarkdown.value))
const needsFallbackHint = computed(
  () => Boolean(selectedReport.value) && (selectedReport.value?.status ?? summary.value?.status) === 'partial',
)
const currentReportWebSearchStatus = computed(() =>
  translateWebSearchStatus(selectedReport.value?.web_search_status),
)
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

const sortedEvents = computed(() => {
  const events = summary.value?.events ?? []
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
    value: String(summary.value?.event_count ?? 0),
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
    return t('analysisWorkbench.watchlistLogin')
  }
  return watchlistItem.value ? t('analysisWorkbench.watchlistRemove') : t('analysisWorkbench.watchlistAdd')
})

const loadSummary = async () => {
  if (!tsCode.value) {
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
    const payload = await analysisApi.getStockAnalysisSummary(tsCode.value, {
      topic: topicContext.value || null,
      eventId: eventId.value || null,
    })
    summary.value = payload
    if (!selectedReportId.value && payload.report?.id) {
      selectedReportId.value = payload.report.id
    }
    selectedEventFilter.value = 'all'
    showAllFactors.value = false
  } catch {
    errorMessage.value = t('analysisWorkbench.error')
    summary.value = null
  } finally {
    loading.value = false
  }
}

const loadReports = async () => {
  if (!tsCode.value) {
    reportArchives.value = []
    return
  }
  try {
    const payload = await analysisApi.getStockAnalysisReports(tsCode.value, 10, {
      topic: topicContext.value || null,
      eventId: eventId.value || null,
    })
    reportArchives.value = payload.items
    if (!selectedReportId.value && payload.items[0]?.id) {
      selectedReportId.value = payload.items[0].id
    }
  } catch {
    reportArchives.value = []
  }
}

const loadWatchlistState = async () => {
  if (!authStore.accessToken || !tsCode.value) {
    watchlistItem.value = null
    return
  }
  try {
    const payload = await watchlistApi.getWatchlist(authStore.accessToken)
    const matchedItem = payload.items.find((item) => item.ts_code === tsCode.value) ?? null
    watchlistItem.value = matchedItem

    // 关键流程：关注页中的联网增强是“自动分析默认值”，分析页只在首次进入该股票时继承一次。
    // 这样既能保持默认一致，又不会在用户手动切换后被异步刷新重新覆盖。
    if (webSearchSeededTsCode.value !== tsCode.value) {
      useWebSearch.value = Boolean(matchedItem?.web_search_enabled)
      webSearchInherited.value = Boolean(matchedItem)
      webSearchSeededTsCode.value = tsCode.value
    }
  } catch {
    watchlistItem.value = null
  }
}

const loadWorkbench = async () => {
  await Promise.all([loadSummary(), loadReports(), loadWatchlistState()])
}

const goToHotNews = async () => {
  await router.push('/news/hot')
}

const goToHome = async () => {
  await router.push('/')
}

const goToStockDetail = async () => {
  if (!tsCode.value) {
    return
  }
  await router.push(`/stocks/${encodeURIComponent(tsCode.value)}`)
}

const goToSource = async () => {
  if (sourceKind.value === 'hot_news') {
    await router.push({
      path: '/news/hot',
      query: topicContext.value ? { topic: topicContext.value } : {},
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
}

const selectReport = (reportId: string | null | undefined) => {
  if (!reportId) {
    return
  }
  selectedReportId.value = reportId
  streamingMarkdown.value = ''
}

const toggleWatchlist = async () => {
  if (!tsCode.value) {
    return
  }
  if (!authStore.accessToken) {
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

const refreshAnalysis = async () => {
  if (!tsCode.value) {
    return
  }

  stopStreaming()
  streaming.value = true
  streamingMarkdown.value = ''

  try {
    const session = await analysisApi.createAnalysisSession(tsCode.value, {
      topic: topicContext.value || null,
      event_id: eventId.value || null,
      force_refresh: true,
      use_web_search: useWebSearch.value,
      trigger_source: 'manual',
    })
    if (session.cached || !session.session_id) {
      streaming.value = false
      await loadWorkbench()
      return
    }

    stopSessionStream = analysisApi.openAnalysisSessionEvents(
      session.session_id,
      {
        onDelta: (payload) => {
          streamingMarkdown.value = String(payload.content ?? '')
        },
        onCompleted: async () => {
          streaming.value = false
          stopStreaming()
          await loadWorkbench()
        },
        onError: (payload) => {
          streaming.value = false
          errorMessage.value = String(payload.detail ?? t('analysisWorkbench.error'))
          stopStreaming()
        },
      },
      { reused: session.reused },
    )
  } catch {
    streaming.value = false
    errorMessage.value = t('analysisWorkbench.error')
  }
}

onMounted(() => {
  void loadWorkbench()
})

onBeforeUnmount(() => {
  stopStreaming()
})

watch(
  () => `${tsCode.value}|${topicContext.value}|${eventId.value}`,
  () => {
    selectedReportId.value = null
    streamingMarkdown.value = ''
    useWebSearch.value = false
    webSearchInherited.value = false
    webSearchSeededTsCode.value = ''
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
          <el-button type="primary" @click="goToHotNews">
            {{ t('analysisWorkbench.emptyHotNewsAction') }}
          </el-button>
          <el-button plain @click="goToHome">
            {{ t('analysisWorkbench.emptyHomeAction') }}
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
        <el-card class="analysis-hero">
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
              v-for="item in overviewItems"
              :key="item.key"
              class="analysis-overview__item"
            >
              <span class="analysis-overview__label">{{ item.label }}</span>
              <strong class="analysis-overview__value">{{ item.value }}</strong>
            </article>
          </div>
        </el-card>

        <div class="analysis-content">
          <div class="analysis-main">
            <el-card class="analysis-panel analysis-panel--summary">
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

              <template v-if="reportAvailable">
                <p v-if="streaming" class="analysis-summary__hint">
                  {{ t('analysisWorkbench.streamHint') }}
                </p>
                <p v-if="needsFallbackHint" class="analysis-summary__hint">
                  {{ t('analysisWorkbench.partialHint') }}
                </p>
                <p v-if="summary?.event_context_message" class="analysis-summary__hint">
                  {{ summary.event_context_message }}
                </p>
                <div
                  v-if="selectedReport?.structured_sources?.length"
                  class="analysis-source-evidence"
                >
                  <span
                    v-for="sourceItem in selectedReport.structured_sources"
                    :key="`${sourceItem.provider}-${sourceItem.count}`"
                    class="analysis-token"
                  >
                    {{ `${sourceItem.provider ?? 'source'} × ${sourceItem.count ?? 0}` }}
                  </span>
                </div>
                <div
                  v-if="selectedReport?.web_sources?.length"
                  class="analysis-web-source-list"
                >
                  <a
                    v-for="webSource in selectedReport.web_sources"
                    :key="`${webSource.url ?? webSource.title}-${webSource.published_at ?? ''}`"
                    class="analysis-web-source-item"
                    :href="webSource.url"
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    <strong>{{ webSource.title ?? webSource.url }}</strong>
                    <span v-if="webSource.source">{{ webSource.source }}</span>
                    <span v-if="webSource.snippet">{{ webSource.snippet }}</span>
                  </a>
                </div>
                <MarkdownContent :source="activeSummaryMarkdown" />
              </template>

              <template v-else-if="withoutReport">
                <p class="analysis-summary__pending-title">{{ t('analysisWorkbench.pendingTitle') }}</p>
                <p class="analysis-summary__body">{{ t('analysisWorkbench.pendingDesc') }}</p>
              </template>

              <template v-else>
                <p class="analysis-summary__body">{{ t('analysisWorkbench.pendingDesc') }}</p>
              </template>
            </el-card>

            <el-card class="analysis-panel">
              <div class="analysis-panel__header">
                <div>
                  <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.historyTitle') }}</p>
                  <h2 class="analysis-panel__title">{{ t('analysisWorkbench.historyTitle') }}</h2>
                </div>
              </div>

              <div v-if="reportArchives.length > 0" class="analysis-history-list">
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
              <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.historyEmpty') }}</p>
            </el-card>

            <el-card class="analysis-panel">
              <div class="analysis-panel__header">
                <div>
                  <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.factorHeading') }}</p>
                  <h2 class="analysis-panel__title">{{ t('analysisWorkbench.factorSubtitle') }}</h2>
                </div>
                <span class="analysis-panel__meta">
                  {{ t('analysisWorkbench.metricTopFactor') }}
                </span>
              </div>

              <div v-if="visibleFactors.length > 0" class="analysis-factor-list">
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
            </el-card>

            <el-card class="analysis-panel">
              <div class="analysis-panel__header">
                <div>
                  <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.riskHeading') }}</p>
                  <h2 class="analysis-panel__title">{{ t('analysisWorkbench.riskSubtitle') }}</h2>
                </div>
              </div>

              <ul v-if="selectedReport?.risk_points?.length" class="analysis-risk-list">
                <li v-for="point in selectedReport?.risk_points" :key="point">
                  {{ point }}
                </li>
              </ul>
              <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.noRisks') }}</p>
            </el-card>
          </div>

          <div class="analysis-side">
            <el-card class="analysis-panel analysis-panel--sticky">
              <div class="analysis-panel__header">
                <div>
                  <p class="analysis-panel__eyebrow">{{ t('analysisWorkbench.eventsHeading') }}</p>
                  <h2 class="analysis-panel__title">{{ t('analysisWorkbench.eventsSubtitle') }}</h2>
                </div>
                <span class="analysis-panel__meta">
                  {{ filteredEvents.length }} / {{ summary?.event_count ?? 0 }}
                </span>
              </div>

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

              <div v-if="filteredEvents.length > 0" class="analysis-event-list">
                <article
                  v-for="event in filteredEvents"
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

                  <div class="analysis-event-card__score">
                    <div class="analysis-event-card__score-head">
                      <span>{{ t('analysisWorkbench.correlation') }}</span>
                      <strong>{{ getCorrelationPercent(event.correlation_score) }}/100</strong>
                    </div>
                    <div class="analysis-score-bar">
                      <span :style="{ width: `${getCorrelationPercent(event.correlation_score)}%` }" />
                    </div>
                  </div>

                  <div class="analysis-event-card__stats">
                    <div>
                      <span>{{ t('analysisWorkbench.windowReturn') }}</span>
                      <strong>{{ formatPercent(event.window_return_pct) }}</strong>
                    </div>
                    <div>
                      <span>{{ t('analysisWorkbench.windowVolatility') }}</span>
                      <strong>{{ formatMetricNumber(event.window_volatility) }}</strong>
                    </div>
                    <div>
                      <span>{{ t('analysisWorkbench.abnormalVolume') }}</span>
                      <strong>{{ formatMetricNumber(event.abnormal_volume_ratio) }}</strong>
                    </div>
                  </div>
                </article>
              </div>
              <p v-else class="analysis-empty-note">{{ t('analysisWorkbench.noEvents') }}</p>
            </el-card>
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
  background:
    linear-gradient(165deg, rgba(15, 23, 38, 0.98), rgba(9, 14, 24, 0.98)),
    rgba(8, 14, 25, 0.95);
  box-shadow: 0 20px 44px rgba(2, 8, 18, 0.28);
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
  color: #eef6ff;
}

.analysis-empty__desc,
.analysis-error__desc,
.analysis-empty-note,
.analysis-panel__meta,
.analysis-hero__generated,
.analysis-hero__code,
.analysis-factor-card__reason,
.analysis-event-card__meta,
.analysis-event-card__stats span,
.analysis-overview__label {
  color: color-mix(in srgb, var(--terminal-muted) 80%, white 20%);
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
  color: color-mix(in srgb, var(--terminal-primary) 84%, white 16%);
}

.analysis-hero {
  padding: 1.2rem;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, rgba(123, 197, 255, 0.12), transparent 36%),
    radial-gradient(circle at bottom left, rgba(87, 184, 255, 0.08), transparent 28%),
    linear-gradient(165deg, rgba(15, 23, 38, 0.98), rgba(8, 14, 25, 0.98));
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
  color: #f5fbff;
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
  background: rgba(10, 18, 29, 0.85);
  color: #eef6ff;
  white-space: nowrap;
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.08);
}

.analysis-status-pill[data-status='ready'] {
  color: #9ff4c2;
  border-color: rgba(18, 183, 106, 0.35);
}

.analysis-status-pill[data-status='partial'] {
  color: #ffd58a;
  border-color: rgba(247, 181, 0, 0.32);
}

.analysis-status-pill[data-status='pending'] {
  color: #a8d5ff;
  border-color: rgba(123, 197, 255, 0.28);
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
  background: rgba(8, 14, 25, 0.76);
  color: color-mix(in srgb, var(--terminal-primary) 88%, white 12%);
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
  background: linear-gradient(180deg, rgba(10, 18, 32, 0.88), rgba(8, 14, 25, 0.74));
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.05);
}

.analysis-hero__action-cluster {
  display: flex;
  align-items: stretch;
  justify-content: flex-end;
  padding: 0.55rem;
  min-width: 0;
  border: 1px solid rgba(123, 197, 255, 0.1);
  border-radius: 18px;
  background: rgba(8, 14, 25, 0.72);
  box-shadow:
    inset 0 0 0 1px rgba(123, 197, 255, 0.04),
    0 12px 32px rgba(0, 0, 0, 0.14);
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
  color: #d9e8f7;
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
  color: color-mix(in srgb, var(--terminal-primary) 62%, white 38%);
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
  box-shadow: 0 10px 24px rgba(64, 158, 255, 0.2);
}

.analysis-action-btn--outline.el-button.is-plain {
  border-color: rgba(123, 197, 255, 0.18);
  background: rgba(10, 18, 32, 0.72);
  color: #eef6ff;
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.05);
}

.analysis-action-btn--outline.el-button.is-plain:hover,
.analysis-action-btn--outline.el-button.is-plain:focus-visible {
  border-color: rgba(123, 197, 255, 0.34);
  background: rgba(20, 34, 56, 0.9);
  color: #f5fbff;
}

.analysis-action-btn--outline.el-button.is-plain:active {
  border-color: rgba(87, 184, 255, 0.42);
  background: rgba(16, 28, 47, 0.96);
}

.analysis-action-btn--outline.el-button.is-disabled,
.analysis-action-btn--outline.el-button.is-plain.is-disabled {
  border-color: rgba(123, 197, 255, 0.12);
  background: rgba(10, 18, 32, 0.42);
  color: rgba(238, 246, 255, 0.52);
}

.analysis-overview {
  margin-top: 1rem;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
}

.analysis-overview__item {
  display: grid;
  gap: 0.36rem;
  padding: 0.78rem 0.85rem;
  border-radius: 14px;
  border: 1px solid rgba(123, 197, 255, 0.08);
  background: rgba(8, 14, 25, 0.72);
}

.analysis-overview__value {
  color: #f5fbff;
  font-size: 1rem;
  line-height: 1.35;
}

.analysis-content {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.95fr);
  gap: 1rem;
  align-items: start;
}

.analysis-main,
.analysis-side {
  display: grid;
  gap: 1rem;
}

.analysis-panel {
  padding: 1rem;
}

.analysis-panel--sticky {
  position: sticky;
  top: 1rem;
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
  color: #f5fbff;
  font-size: 1.05rem;
}

.analysis-summary__hint {
  margin: 0 0 0.8rem;
  padding: 0.7rem 0.8rem;
  border-radius: 12px;
  border: 1px solid rgba(247, 181, 0, 0.18);
  background: rgba(53, 38, 7, 0.34);
  color: #ffd58a;
}

.analysis-source-evidence {
  margin-bottom: 0.8rem;
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.analysis-web-source-list {
  margin-bottom: 0.8rem;
  display: grid;
  gap: 0.6rem;
}

.analysis-web-source-item {
  display: grid;
  gap: 0.2rem;
  padding: 0.75rem 0.85rem;
  border-radius: 12px;
  border: 1px solid rgba(123, 197, 255, 0.14);
  background: rgba(8, 14, 25, 0.58);
  color: #d9e8f7;
  text-decoration: none;
}

.analysis-web-source-item strong {
  color: #f5fbff;
}

.analysis-summary__body {
  margin: 0;
  color: #e7f0fb;
  line-height: 1.8;
  font-size: 0.98rem;
}

.analysis-summary__pending-title {
  margin: 0 0 0.4rem;
  color: #f5fbff;
  font-weight: 600;
}

.analysis-factor-list,
.analysis-event-list,
.analysis-history-list {
  display: grid;
  gap: 0.75rem;
}

.analysis-history-item,
.analysis-factor-card,
.analysis-event-card {
  border-radius: 14px;
  border: 1px solid rgba(123, 197, 255, 0.08);
  background: rgba(8, 14, 25, 0.64);
  padding: 0.82rem 0.88rem;
}

.analysis-event-card--anchor {
  border-color: rgba(123, 197, 255, 0.32);
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.08);
}

.analysis-history-item {
  display: grid;
  gap: 0.24rem;
  text-align: left;
  color: #f5fbff;
  cursor: pointer;
}

.analysis-history-item.active {
  border-color: rgba(123, 197, 255, 0.32);
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
  color: #f5fbff;
  font-weight: 600;
}

.analysis-factor-card__reason,
.analysis-event-card__meta {
  margin: 0.25rem 0 0;
  font-size: 0.84rem;
}

.analysis-factor-card__meta {
  display: grid;
  justify-items: end;
  gap: 0.2rem;
  color: #e7f0fb;
  text-align: right;
}

.analysis-factor-card__bar,
.analysis-score-bar {
  margin-top: 0.78rem;
  height: 0.48rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.analysis-factor-card__bar span,
.analysis-score-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(87, 184, 255, 0.95), rgba(123, 197, 255, 0.55));
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
  background: rgba(9, 16, 29, 0.84);
  color: #d9e8f7;
  cursor: pointer;
  transition: 0.2s ease;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
}

.analysis-filter-chip.active {
  background: linear-gradient(120deg, rgba(87, 184, 255, 0.2), rgba(123, 197, 255, 0.08));
  border-color: rgba(123, 197, 255, 0.3);
  color: #f5fbff;
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
  color: #f5fbff;
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
  color: #eef6ff;
  line-height: 1.6;
}

.analysis-token--confidence {
  color: #eef6ff;
}

@media (max-width: 1040px) {
  .analysis-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .analysis-content {
    grid-template-columns: 1fr;
  }

  .analysis-panel--sticky {
    position: static;
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
