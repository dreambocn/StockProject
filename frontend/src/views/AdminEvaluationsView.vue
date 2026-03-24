<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { ECharts } from 'echarts'
import { useI18n } from 'vue-i18n'

import {
  evaluationsApi,
  type EvaluationCaseComparison,
  type EvaluationCaseDetailResponse,
  type EvaluationCatalogResponse,
  type EvaluationExperimentGroup,
  type EvaluationOverviewResponse,
  type EvaluationRunSummary,
} from '../api/evaluations'
import { ApiError } from '../api/http'
import { useAuthStore } from '../stores/auth'
import { mapApiErrorMessage } from '../utils/apiErrorI18n'

const authStore = useAuthStore()
const { t } = useI18n()

const loadingCatalog = ref(false)
const loadingOverview = ref(false)
const loadingCase = ref(false)
const errorMessage = ref('')

const catalog = ref<EvaluationCatalogResponse | null>(null)
const overview = ref<EvaluationOverviewResponse | null>(null)
const activeCaseDetail = ref<EvaluationCaseDetailResponse | null>(null)
const caseDrawerVisible = ref(false)

const selectedDatasetKey = ref('')
const selectedExperimentGroupKey = ref('')
const selectedBaselineRunId = ref('')
const selectedCandidateRunId = ref('')

const barChartEl = ref<HTMLDivElement | null>(null)
const distributionChartEl = ref<HTMLDivElement | null>(null)
let barChart: ECharts | null = null
let distributionChart: ECharts | null = null
let echartsModulePromise: Promise<typeof import('echarts')> | null = null

const accessToken = computed(() => authStore.accessToken)
const currentMetricCards = computed(() =>
  Object.values(overview.value?.metric_cards ?? {}),
)
const availableExperimentGroups = computed(() =>
  (catalog.value?.experiment_groups ?? []).filter(
    (item) => item.dataset_key === selectedDatasetKey.value,
  ),
)
const currentExperimentGroup = computed<EvaluationExperimentGroup | null>(() => {
  return (
    availableExperimentGroups.value.find(
      (item) => item.experiment_group_key === selectedExperimentGroupKey.value,
    ) ?? null
  )
})
const baselineRunOptions = computed<EvaluationRunSummary[]>(
  () => currentExperimentGroup.value?.baseline_runs ?? [],
)
const candidateRunOptions = computed<EvaluationRunSummary[]>(
  () => currentExperimentGroup.value?.candidate_runs ?? [],
)
const isOverviewEmpty = computed(
  () => !overview.value || overview.value.empty || !overview.value.baseline_run,
)

const loadECharts = () => {
  echartsModulePromise ??= import('echarts')
  return echartsModulePromise
}

const resolveExperimentDefaults = () => {
  const firstDataset =
    catalog.value?.datasets.find(
      (item) => item.dataset_key === selectedDatasetKey.value,
    ) ?? catalog.value?.datasets[0]
  selectedDatasetKey.value = firstDataset?.dataset_key ?? ''

  const firstGroup =
    availableExperimentGroups.value.find(
      (item) => item.experiment_group_key === selectedExperimentGroupKey.value,
    ) ?? availableExperimentGroups.value[0]
  selectedExperimentGroupKey.value = firstGroup?.experiment_group_key ?? ''
  selectedBaselineRunId.value =
    firstGroup?.latest_baseline_run?.id ?? firstGroup?.baseline_runs[0]?.id ?? ''
  selectedCandidateRunId.value =
    firstGroup?.latest_candidate_run?.id ?? firstGroup?.candidate_runs[0]?.id ?? ''
}

const formatPercent = (value: number) => `${(value * 100).toFixed(0)}%`

const formatMetricValue = (value: number, unit: string) => {
  if (unit === 'rate') {
    return formatPercent(value)
  }
  return `${Math.round(value)} ms`
}

const formatDateRange = () => {
  if (!overview.value?.dataset) {
    return '--'
  }
  const { date_from, date_to } = overview.value.dataset
  if (!date_from && !date_to) {
    return '--'
  }
  return `${date_from || '--'} ~ ${date_to || '--'}`
}

const resolveClassificationLabel = (value: string) => {
  return t(`adminEvaluations.classification.${value}`)
}

const resolveClassificationTag = (value: string) => {
  if (value === 'improved') {
    return 'success'
  }
  if (value === 'regressed') {
    return 'danger'
  }
  return 'info'
}

const formatScoreDelta = (value: number) => {
  const normalized = value.toFixed(2)
  return value > 0 ? `+${normalized}` : normalized
}

const renderCharts = async () => {
  if (
    typeof window === 'undefined' ||
    typeof window.ResizeObserver !== 'function' ||
    !overview.value ||
    overview.value.empty ||
    !barChartEl.value ||
    !distributionChartEl.value
  ) {
    return
  }

  const echarts = await loadECharts()
  barChart ??= echarts.init(barChartEl.value)
  distributionChart ??= echarts.init(distributionChartEl.value)

  // 图表只做展示，不参与业务判断；颜色保持与后台 Neo Terminal 视觉语言一致。
  barChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      textStyle: { color: '#d9e2ff' },
      data: [t('adminEvaluations.summary.baseline'), t('adminEvaluations.summary.candidate')],
    },
    xAxis: {
      type: 'category',
      data: overview.value.bar_chart.categories,
      axisLabel: { color: '#9fb0d1' },
      axisLine: { lineStyle: { color: 'rgba(123, 197, 255, 0.25)' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#9fb0d1' },
      splitLine: { lineStyle: { color: 'rgba(123, 197, 255, 0.12)' } },
    },
    series: [
      {
        name: t('adminEvaluations.summary.baseline'),
        type: 'bar',
        itemStyle: { color: '#7bc5ff' },
        data: overview.value.bar_chart.baseline_series,
      },
      {
        name: t('adminEvaluations.summary.candidate'),
        type: 'bar',
        itemStyle: { color: '#f7b500' },
        data: overview.value.bar_chart.candidate_series,
      },
    ],
  })

  distributionChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: {
      bottom: 0,
      textStyle: { color: '#d9e2ff' },
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        label: { color: '#d9e2ff' },
        data: [
          {
            value: overview.value.distribution_chart.improved,
            name: resolveClassificationLabel('improved'),
            itemStyle: { color: '#18b26a' },
          },
          {
            value: overview.value.distribution_chart.unchanged,
            name: resolveClassificationLabel('unchanged'),
            itemStyle: { color: '#7bc5ff' },
          },
          {
            value: overview.value.distribution_chart.regressed,
            name: resolveClassificationLabel('regressed'),
            itemStyle: { color: '#f75371' },
          },
        ],
      },
    ],
  })
}

const disposeCharts = () => {
  barChart?.dispose()
  distributionChart?.dispose()
  barChart = null
  distributionChart = null
}

const loadOverview = async () => {
  if (
    !accessToken.value ||
    !selectedDatasetKey.value ||
    !selectedExperimentGroupKey.value
  ) {
    overview.value = null
    return
  }

  loadingOverview.value = true
  errorMessage.value = ''
  try {
    overview.value = await evaluationsApi.getOverview(accessToken.value, {
      datasetKey: selectedDatasetKey.value,
      experimentGroupKey: selectedExperimentGroupKey.value,
      baselineRunId: selectedBaselineRunId.value || undefined,
      candidateRunId: selectedCandidateRunId.value || undefined,
    })
    await renderCharts()
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    loadingOverview.value = false
  }
}

const loadCatalog = async () => {
  if (!accessToken.value) {
    return
  }
  loadingCatalog.value = true
  errorMessage.value = ''
  try {
    catalog.value = await evaluationsApi.getCatalog(accessToken.value)
    resolveExperimentDefaults()
    await loadOverview()
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    loadingCatalog.value = false
  }
}

const handleDatasetChange = async () => {
  selectedExperimentGroupKey.value =
    availableExperimentGroups.value[0]?.experiment_group_key ?? ''
  selectedBaselineRunId.value =
    availableExperimentGroups.value[0]?.latest_baseline_run?.id ??
    availableExperimentGroups.value[0]?.baseline_runs[0]?.id ??
    ''
  selectedCandidateRunId.value =
    availableExperimentGroups.value[0]?.latest_candidate_run?.id ??
    availableExperimentGroups.value[0]?.candidate_runs[0]?.id ??
    ''
  await loadOverview()
}

const handleExperimentGroupChange = async () => {
  selectedBaselineRunId.value =
    currentExperimentGroup.value?.latest_baseline_run?.id ??
    currentExperimentGroup.value?.baseline_runs[0]?.id ??
    ''
  selectedCandidateRunId.value =
    currentExperimentGroup.value?.latest_candidate_run?.id ??
    currentExperimentGroup.value?.candidate_runs[0]?.id ??
    ''
  await loadOverview()
}

const handleRunChange = async () => {
  await loadOverview()
}

const openCaseDetail = async (caseKey: string) => {
  if (
    !accessToken.value ||
    !selectedBaselineRunId.value ||
    !selectedCandidateRunId.value
  ) {
    return
  }
  loadingCase.value = true
  try {
    activeCaseDetail.value = await evaluationsApi.getCaseDetail(
      accessToken.value,
      caseKey,
      {
        baselineRunId: selectedBaselineRunId.value,
        candidateRunId: selectedCandidateRunId.value,
      },
    )
    caseDrawerVisible.value = true
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    loadingCase.value = false
  }
}

const renderCaseList = (items: EvaluationCaseComparison[]) => items.slice(0, 3)

onMounted(async () => {
  await loadCatalog()
})

onBeforeUnmount(() => {
  disposeCharts()
})
</script>

<template>
  <section
    class="admin-evaluations-page"
    v-motion
    :initial="{ opacity: 0, y: 18 }"
    :enter="{ opacity: 1, y: 0 }"
  >
    <header class="hero-card">
      <div>
        <p class="panel-kicker">{{ t('adminEvaluations.kicker') }}</p>
        <h1>{{ t('adminEvaluations.title') }}</h1>
        <p class="section-note">{{ t('adminEvaluations.note') }}</p>
      </div>
      <div class="hero-summary">
        <div class="hero-chip">
          <span>{{ t('adminEvaluations.summary.sampleCount') }}</span>
          <strong>{{ overview?.dataset?.sample_count ?? 0 }}</strong>
        </div>
        <div class="hero-chip">
          <span>{{ t('adminEvaluations.summary.dateRange') }}</span>
          <strong>{{ formatDateRange() }}</strong>
        </div>
      </div>
    </header>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    />

    <el-card class="admin-card" shadow="never">
      <div class="filters-grid">
        <div class="filter-field">
          <label>{{ t('adminEvaluations.filters.dataset') }}</label>
          <el-select
            v-model="selectedDatasetKey"
            data-testid="dataset-select"
            :loading="loadingCatalog"
            @change="handleDatasetChange"
          >
            <el-option
              v-for="item in catalog?.datasets ?? []"
              :key="item.dataset_key"
              :label="item.label"
              :value="item.dataset_key"
            />
          </el-select>
        </div>
        <div class="filter-field">
          <label>{{ t('adminEvaluations.filters.experimentGroup') }}</label>
          <el-select
            v-model="selectedExperimentGroupKey"
            data-testid="experiment-group-select"
            :loading="loadingCatalog"
            @change="handleExperimentGroupChange"
          >
            <el-option
              v-for="item in availableExperimentGroups"
              :key="item.experiment_group_key"
              :label="item.experiment_group_key"
              :value="item.experiment_group_key"
            />
          </el-select>
        </div>
        <div class="filter-field">
          <label>{{ t('adminEvaluations.filters.baselineRun') }}</label>
          <el-select
            v-model="selectedBaselineRunId"
            data-testid="baseline-run-select"
            :loading="loadingOverview"
            @change="handleRunChange"
          >
            <el-option
              v-for="item in baselineRunOptions"
              :key="item.id"
              :label="`${item.run_key} · ${item.prompt_profile_key}`"
              :value="item.id"
            />
          </el-select>
        </div>
        <div class="filter-field">
          <label>{{ t('adminEvaluations.filters.candidateRun') }}</label>
          <el-select
            v-model="selectedCandidateRunId"
            data-testid="candidate-run-select"
            :loading="loadingOverview"
            @change="handleRunChange"
          >
            <el-option
              v-for="item in candidateRunOptions"
              :key="item.id"
              :label="`${item.run_key} · ${item.prompt_profile_key}`"
              :value="item.id"
            />
          </el-select>
        </div>
      </div>
    </el-card>

    <template v-if="isOverviewEmpty">
      <el-card class="admin-card empty-card" shadow="never">
        <p class="mini-kicker">{{ t('adminEvaluations.empty.title') }}</p>
        <p class="section-note">{{ t('adminEvaluations.empty.note') }}</p>
        <div class="cli-grid">
          <div class="cli-card">
            <strong>{{ t('adminEvaluations.empty.importCommand') }}</strong>
            <code>Set-Location 'E:\Development\Project\StockProject\backend'; uv run python scripts\import_analysis_evaluation_dataset.py</code>
          </div>
          <div class="cli-card">
            <strong>{{ t('adminEvaluations.empty.runCommand') }}</strong>
            <code>Set-Location 'E:\Development\Project\StockProject\backend'; uv run python scripts\run_analysis_evaluation.py --dataset-key analysis_eval_dataset_v1 --experiment-group-key prompt_profile_compare_v1</code>
          </div>
        </div>
      </el-card>
    </template>

    <template v-else>
      <section class="metric-grid">
        <article v-for="item in currentMetricCards" :key="item.metric_key" class="metric-card">
          <span>{{ item.label }}</span>
          <strong>{{ formatMetricValue(item.candidate_value, item.unit) }}</strong>
          <em>
            {{ t('adminEvaluations.summary.baseline') }} {{ formatMetricValue(item.baseline_value, item.unit) }}
          </em>
        </article>
      </section>

      <section class="chart-grid">
        <el-card class="admin-card chart-card" shadow="never">
          <div class="card-head">
            <div>
              <p class="mini-kicker">ECHARTS</p>
              <h2>{{ t('adminEvaluations.charts.metricCompare') }}</h2>
            </div>
          </div>
          <div ref="barChartEl" data-testid="evaluation-bar-chart" class="chart-box" />
        </el-card>
        <el-card class="admin-card chart-card" shadow="never">
          <div class="card-head">
            <div>
              <p class="mini-kicker">ECHARTS</p>
              <h2>{{ t('adminEvaluations.charts.distribution') }}</h2>
            </div>
          </div>
          <div
            ref="distributionChartEl"
            data-testid="evaluation-distribution-chart"
            class="chart-box"
          />
        </el-card>
      </section>

      <section class="case-grid">
        <el-card class="admin-card" shadow="never">
          <div class="card-head">
            <div>
              <p class="mini-kicker">TOP CASES</p>
              <h2>{{ t('adminEvaluations.sections.improved') }}</h2>
            </div>
          </div>
          <button
            v-for="item in renderCaseList(overview?.top_improved_cases ?? [])"
            :key="item.case_key"
            class="case-card success"
            @click="openCaseDetail(item.case_key)"
          >
            <strong>{{ item.ts_code }}</strong>
            <span>{{ item.anchor_event_title }}</span>
            <em>{{ formatScoreDelta(item.score_delta) }}</em>
          </button>
        </el-card>

        <el-card class="admin-card" shadow="never">
          <div class="card-head">
            <div>
              <p class="mini-kicker">TOP CASES</p>
              <h2>{{ t('adminEvaluations.sections.regressed') }}</h2>
            </div>
          </div>
          <button
            v-for="item in renderCaseList(overview?.top_regressed_cases ?? [])"
            :key="item.case_key"
            class="case-card danger"
            @click="openCaseDetail(item.case_key)"
          >
            <strong>{{ item.ts_code }}</strong>
            <span>{{ item.anchor_event_title }}</span>
            <em>{{ formatScoreDelta(item.score_delta) }}</em>
          </button>
        </el-card>
      </section>

      <el-card class="admin-card" shadow="never">
        <div class="card-head">
          <div>
            <p class="mini-kicker">RECENT CASES</p>
            <h2>{{ t('adminEvaluations.sections.recent') }}</h2>
          </div>
        </div>
        <div class="case-table">
          <button
            v-for="item in overview?.recent_cases ?? []"
            :key="item.case_key"
            :data-testid="`case-row-${item.case_key}`"
            class="case-row"
            @click="openCaseDetail(item.case_key)"
          >
            <div>
              <strong>{{ item.case_key }}</strong>
              <span>{{ item.ts_code }}</span>
            </div>
            <div>{{ item.anchor_event_title }}</div>
            <el-tag :type="resolveClassificationTag(item.classification)">
              {{ resolveClassificationLabel(item.classification) }}
            </el-tag>
            <div>{{ formatScoreDelta(item.score_delta) }}</div>
          </button>
        </div>
      </el-card>
    </template>

    <el-drawer
      v-model="caseDrawerVisible"
      :title="t('adminEvaluations.sections.detail')"
      size="42%"
    >
      <div v-if="activeCaseDetail" class="drawer-content">
        <div class="detail-meta">
          <div>
            <span>{{ t('adminEvaluations.detail.anchorEvent') }}</span>
            <strong>{{ activeCaseDetail.case.anchor_event_title }}</strong>
          </div>
          <div>
            <span>{{ t('adminEvaluations.detail.expectedFactor') }}</span>
            <strong>{{ activeCaseDetail.case.expected_top_factor_key }}</strong>
          </div>
          <div>
            <span>{{ t('adminEvaluations.detail.topic') }}</span>
            <strong>{{ activeCaseDetail.case.topic || '--' }}</strong>
          </div>
          <div>
            <span>{{ t('adminEvaluations.detail.note') }}</span>
            <strong>{{ activeCaseDetail.case.notes || '--' }}</strong>
          </div>
        </div>

        <div class="detail-compare-grid">
          <article class="compare-card">
            <p class="mini-kicker">{{ t('adminEvaluations.sections.baseline') }}</p>
            <h3>{{ activeCaseDetail.baseline_run.prompt_profile_key }}</h3>
            <ul class="detail-list">
              <li>{{ t('adminEvaluations.detail.topEvent') }}：{{ activeCaseDetail.baseline_result.top_event_title || '--' }}</li>
              <li>{{ t('adminEvaluations.detail.topFactor') }}：{{ activeCaseDetail.baseline_result.top_factor_key || '--' }}</li>
              <li>{{ t('adminEvaluations.detail.citationRate') }}：{{ formatPercent(activeCaseDetail.baseline_result.citation_metadata_completeness_rate) }}</li>
              <li>{{ t('adminEvaluations.detail.citationCount') }}：{{ activeCaseDetail.baseline_result.web_source_count }}</li>
              <li>{{ t('adminEvaluations.detail.latency') }}：{{ Math.round(activeCaseDetail.baseline_result.latency_ms) }} ms</li>
              <li>{{ t('adminEvaluations.detail.score') }}：{{ activeCaseDetail.baseline_result.case_score.toFixed(2) }}</li>
            </ul>
            <p class="summary-box">
              {{ activeCaseDetail.baseline_result.result_snapshot?.summary || '--' }}
            </p>
          </article>

          <article class="compare-card candidate">
            <p class="mini-kicker">{{ t('adminEvaluations.sections.candidate') }}</p>
            <h3>{{ activeCaseDetail.candidate_run.prompt_profile_key }}</h3>
            <ul class="detail-list">
              <li>{{ t('adminEvaluations.detail.topEvent') }}：{{ activeCaseDetail.candidate_result.top_event_title || '--' }}</li>
              <li>{{ t('adminEvaluations.detail.topFactor') }}：{{ activeCaseDetail.candidate_result.top_factor_key || '--' }}</li>
              <li>{{ t('adminEvaluations.detail.citationRate') }}：{{ formatPercent(activeCaseDetail.candidate_result.citation_metadata_completeness_rate) }}</li>
              <li>{{ t('adminEvaluations.detail.citationCount') }}：{{ activeCaseDetail.candidate_result.web_source_count }}</li>
              <li>{{ t('adminEvaluations.detail.latency') }}：{{ Math.round(activeCaseDetail.candidate_result.latency_ms) }} ms</li>
              <li>{{ t('adminEvaluations.detail.score') }}：{{ activeCaseDetail.candidate_result.case_score.toFixed(2) }}</li>
            </ul>
            <p class="summary-box">
              {{ activeCaseDetail.candidate_result.result_snapshot?.summary || '--' }}
            </p>
          </article>
        </div>
      </div>
      <div v-else class="section-note">{{ loadingCase ? t('adminEvaluations.loading') : '--' }}</div>
    </el-drawer>
  </section>
</template>

<style scoped>
.admin-evaluations-page {
  display: grid;
  gap: 1rem;
}

.hero-card,
.admin-card {
  border: 1px solid var(--terminal-border);
  border-radius: 18px;
  background:
    radial-gradient(circle at 86% 12%, rgba(123, 197, 255, 0.18), transparent 42%),
    linear-gradient(145deg, rgba(19, 29, 48, 0.95), rgba(9, 16, 30, 0.97));
  box-shadow: var(--terminal-shadow);
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.05rem;
}

.panel-kicker,
.mini-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.panel-kicker {
  color: #f7b500;
  font-size: 0.74rem;
}

.mini-kicker {
  color: #7bc5ff;
  font-size: 0.66rem;
}

h1,
h2,
h3 {
  margin: 0.28rem 0 0;
}

.section-note {
  margin: 0.28rem 0 0;
  color: var(--terminal-muted);
}

.hero-summary,
.metric-grid,
.chart-grid,
.case-grid,
.detail-compare-grid {
  display: grid;
  gap: 1rem;
}

.hero-summary {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.hero-chip,
.metric-card,
.case-card,
.compare-card,
.cli-card {
  border: 1px solid color-mix(in srgb, var(--terminal-border) 78%, transparent);
  border-radius: 14px;
  background: linear-gradient(160deg, rgba(20, 32, 54, 0.95), rgba(10, 18, 32, 0.97));
}

.hero-chip {
  padding: 0.8rem;
  display: grid;
  gap: 0.25rem;
}

.hero-chip span,
.metric-card span,
.detail-meta span {
  color: var(--terminal-muted);
  font-size: 0.74rem;
}

.hero-chip strong,
.metric-card strong {
  font-size: 1.15rem;
}

.filters-grid,
.metric-grid,
.chart-grid,
.case-grid,
.detail-meta {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.filters-grid {
  display: grid;
  gap: 0.85rem;
}

.filter-field {
  display: grid;
  gap: 0.4rem;
}

.filter-field label {
  font-size: 0.76rem;
  color: var(--terminal-muted);
}

.empty-card {
  padding: 1rem;
}

.cli-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.cli-card {
  padding: 0.95rem;
  display: grid;
  gap: 0.45rem;
}

.cli-card code {
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'IBM Plex Mono', monospace;
  color: #d9e2ff;
}

.metric-card {
  padding: 0.85rem;
  display: grid;
  gap: 0.25rem;
}

.metric-card em {
  color: var(--terminal-muted);
  font-style: normal;
}

.chart-card {
  padding-bottom: 0.6rem;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.chart-box {
  width: 100%;
  min-height: 320px;
}

.case-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.case-card,
.case-row {
  width: 100%;
  padding: 0.85rem;
  display: grid;
  gap: 0.25rem;
  text-align: left;
  color: var(--terminal-text);
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.case-card.success {
  box-shadow: inset 0 0 0 1px rgba(24, 178, 106, 0.2);
}

.case-card.danger {
  box-shadow: inset 0 0 0 1px rgba(247, 83, 113, 0.2);
}

.case-card:hover,
.case-row:hover {
  transform: translateY(-2px);
  border-color: rgba(123, 197, 255, 0.45);
}

.case-card strong,
.case-row strong {
  font-size: 0.96rem;
}

.case-card span,
.case-row span {
  color: var(--terminal-muted);
}

.case-card em {
  font-style: normal;
  color: #f7b500;
}

.case-table {
  display: grid;
  gap: 0.65rem;
}

.case-row {
  border: 1px solid color-mix(in srgb, var(--terminal-border) 74%, transparent);
  border-radius: 14px;
  background: linear-gradient(160deg, rgba(20, 32, 54, 0.95), rgba(10, 18, 32, 0.97));
  grid-template-columns: 1.15fr 2fr auto auto;
  align-items: center;
}

.drawer-content {
  display: grid;
  gap: 1rem;
}

.detail-meta {
  display: grid;
  gap: 0.75rem;
}

.detail-meta > div,
.compare-card {
  padding: 0.9rem;
}

.detail-meta > div {
  border: 1px solid color-mix(in srgb, var(--terminal-border) 75%, transparent);
  border-radius: 14px;
  background: linear-gradient(160deg, rgba(20, 32, 54, 0.95), rgba(10, 18, 32, 0.97));
  display: grid;
  gap: 0.25rem;
}

.detail-compare-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.compare-card.candidate {
  box-shadow: inset 0 0 0 1px rgba(247, 181, 0, 0.18);
}

.detail-list {
  margin: 0.75rem 0 0;
  padding-left: 1rem;
  display: grid;
  gap: 0.35rem;
}

.summary-box {
  margin: 0.85rem 0 0;
  border-radius: 12px;
  padding: 0.85rem;
  background: rgba(7, 13, 24, 0.58);
  color: #d9e2ff;
  line-height: 1.6;
}

@media (max-width: 1100px) {
  .filters-grid,
  .metric-grid,
  .detail-meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-grid,
  .case-grid,
  .detail-compare-grid,
  .cli-grid {
    grid-template-columns: 1fr;
  }

  .case-row {
    grid-template-columns: 1fr;
    justify-items: start;
  }

  .hero-card {
    flex-direction: column;
  }
}
</style>
