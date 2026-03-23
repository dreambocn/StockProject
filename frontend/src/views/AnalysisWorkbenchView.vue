<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import type { StockAnalysisSummaryResponse } from '../api/analysis'
import { analysisApi } from '../api/analysis'

const route = useRoute()
const { t } = useI18n()

const tsCode = computed(() => String(route.query.ts_code ?? '').trim().toUpperCase())
const source = computed(() => String(route.query.source ?? '').trim())
const topicContext = computed(() => String(route.query.topic ?? '').trim())
const eventId = computed(() => String(route.query.event_id ?? '').trim())
const summary = ref<StockAnalysisSummaryResponse | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const hasTsCode = computed(() => Boolean(tsCode.value))
const reportAvailable = computed(() => Boolean(summary.value?.report))
const needsFallbackHint = computed(
  () => Boolean(summary.value?.report) && summary.value?.status !== 'ready',
)
const withoutReport = computed(() => Boolean(summary.value && !summary.value.report))
const contextItems = computed(() =>
  [
    source.value ? `${t('analysisWorkbench.contextSource')}: ${source.value}` : null,
    topicContext.value ? `${t('analysisWorkbench.contextTopic')}: ${topicContext.value}` : null,
    eventId.value ? `${t('analysisWorkbench.contextEvent')}: ${eventId.value}` : null,
  ].filter((item): item is string => Boolean(item)),
)

const loadSummary = async () => {
  if (!tsCode.value) {
    summary.value = null
    errorMessage.value = ''
    loading.value = false
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    summary.value = await analysisApi.getStockAnalysisSummary(tsCode.value)
  } catch (error) {
    errorMessage.value = t('analysisWorkbench.error')
    summary.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadSummary()
})

watch(
  () => tsCode.value,
  () => {
    loadSummary()
  },
)
</script>

<template>
  <section class="analysis-workbench">
    <el-card v-if="!hasTsCode" class="analysis-empty">
      <p class="analysis-empty__title">{{ t('analysisWorkbench.emptyTitle') }}</p>
      <p class="analysis-empty__desc">{{ t('analysisWorkbench.emptyDesc') }}</p>
    </el-card>

    <el-card v-else-if="errorMessage" class="analysis-error">
      <p>{{ errorMessage }}</p>
    </el-card>

    <el-card v-else-if="loading" class="analysis-loading">
      <el-skeleton :rows="5" animated />
    </el-card>

    <template v-else>
      <el-card class="analysis-context">
        <div class="analysis-context__header">
          <div>
            <p class="analysis-context__label">{{ t('analysisWorkbench.panelTitle') }}</p>
            <h2 class="analysis-context__title">{{ summary?.instrument?.name ?? tsCode }}</h2>
            <p class="analysis-context__code">{{ summary?.ts_code ?? tsCode }}</p>
            <div v-if="contextItems.length > 0" class="analysis-context__tags">
              <span v-for="item in contextItems" :key="item" class="analysis-context__tag">
                {{ item }}
              </span>
            </div>
          </div>
          <div class="analysis-context__meta">
            <p>
              <strong>{{ t('analysisWorkbench.latestSnapshot') }}:</strong>
              {{ summary?.latest_snapshot?.close ?? t('analysisWorkbench.dataMissing') }}
            </p>
            <p>
              <strong>{{ t('analysisWorkbench.statusLabel') }}:</strong>
              {{ summary?.status ?? t('analysisWorkbench.pendingStatus') }}
            </p>
          </div>
        </div>
      </el-card>

      <el-card class="analysis-summary" v-if="reportAvailable">
        <p class="analysis-summary__heading">{{ t('analysisWorkbench.summaryTitle') }}</p>
        <p v-if="needsFallbackHint" class="analysis-summary__hint">
          {{ t('analysisWorkbench.partialHint') }}
        </p>
        <p class="analysis-summary__body">{{ summary?.report?.summary }}</p>
      </el-card>

      <el-card class="analysis-summary" v-else-if="withoutReport">
        <p class="analysis-summary__heading">{{ t('analysisWorkbench.pendingTitle') }}</p>
        <p class="analysis-summary__body">{{ t('analysisWorkbench.pendingDesc') }}</p>
      </el-card>

      <el-card class="analysis-factors" v-if="summary?.report?.factor_breakdown?.length">
        <p class="analysis-factors__heading">{{ t('analysisWorkbench.factorHeading') }}</p>
        <ul class="analysis-factors__list">
          <li v-for="factor in summary?.report?.factor_breakdown" :key="factor.factor_key">
            <div>
              <strong>{{ factor.factor_label }}</strong>
              <p class="analysis-factors__weight">{{ factor.weight }}</p>
            </div>
            <p class="analysis-factors__direction">{{ factor.direction }}</p>
            <p class="analysis-factors__reason">{{ factor.reason }}</p>
          </li>
        </ul>
      </el-card>

      <el-card class="analysis-events" v-if="summary?.events?.length">
        <p class="analysis-events__heading">{{ t('analysisWorkbench.eventsHeading') }}</p>
        <ul>
          <li v-for="event in summary?.events" :key="event.event_id">
            <p class="analysis-events__title">{{ event.title }}</p>
            <p class="analysis-events__meta">
              {{ event.macro_topic || t('analysisWorkbench.noTopic') }} · {{ event.event_type || t('analysisWorkbench.noEventType') }}
            </p>
            <div class="analysis-events__stats">
              <span>{{ t('analysisWorkbench.correlation') }}: {{ event.correlation_score ?? '--' }}</span>
              <span>{{ t('analysisWorkbench.sentiment') }}: {{ event.sentiment_label ?? '--' }}</span>
            </div>
          </li>
        </ul>
      </el-card>

      <el-card class="analysis-risk" v-if="summary?.report?.risk_points?.length">
        <p class="analysis-risk__heading">{{ t('analysisWorkbench.riskHeading') }}</p>
        <ul>
          <li v-for="point in summary?.report?.risk_points" :key="point">{{ point }}</li>
        </ul>
      </el-card>
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
.analysis-loading,
.analysis-context,
.analysis-summary,
.analysis-factors,
.analysis-events,
.analysis-risk {
  border-radius: 14px;
  border: 1px solid var(--terminal-border);
  background: rgba(12, 20, 33, 0.85);
}

.analysis-empty {
  text-align: center;
  padding: 2rem;
}

.analysis-empty__title {
  font-size: 1.2rem;
  margin-bottom: 0.4rem;
  color: var(--terminal-primary);
}

.analysis-context__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.analysis-context__title {
  margin: 0.2rem 0;
  font-size: 1.4rem;
}

.analysis-context__code {
  margin: 0;
  color: var(--terminal-muted);
}

.analysis-context__tags {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  margin-top: 0.65rem;
}

.analysis-context__tag {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(123, 197, 255, 0.25);
  border-radius: 999px;
  padding: 0.18rem 0.58rem;
  color: var(--terminal-primary);
  font-size: 0.76rem;
  font-family: 'IBM Plex Mono', monospace;
  background: rgba(8, 14, 25, 0.74);
}

.analysis-context__meta {
  text-align: right;
  font-size: 0.9rem;
}

.analysis-summary__heading,
.analysis-factors__heading,
.analysis-events__heading,
.analysis-risk__heading {
  font-weight: 600;
  color: var(--terminal-primary);
  margin-bottom: 0.6rem;
}

.analysis-summary__body {
  line-height: 1.6;
}

.analysis-summary__hint {
  margin: 0 0 0.5rem;
  color: var(--terminal-warning, #f7b500);
  font-size: 0.82rem;
}

.analysis-factors__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.analysis-factors__list li {
  display: flex;
  justify-content: space-between;
  padding: 0.4rem 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.analysis-events__stats {
  display: flex;
  gap: 1rem;
  font-size: 0.85rem;
  color: var(--terminal-muted);
}

.analysis-risk ul,
.analysis-events ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.analysis-risk li {
  padding-left: 0.5rem;
  border-left: 2px solid var(--terminal-primary);
}

@media (max-width: 760px) {
  .analysis-context__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .analysis-context__meta {
    text-align: left;
  }

  .analysis-factors__list li {
    display: grid;
    gap: 0.3rem;
  }
}
</style>
