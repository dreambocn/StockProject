<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  adminApi,
  type EvaluationCaseResult,
  type EvaluationDatasetOption,
  type EvaluationMetricBreakdown,
  type EvaluationRunDetail,
  type EvaluationRunListItem,
} from '../api/admin'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const datasets = ref<EvaluationDatasetOption[]>([])
const runs = ref<EvaluationRunListItem[]>([])
const selectedRun = ref<EvaluationRunDetail | null>(null)
const selectedDataset = ref('default_research_cases')
const selectedProfile = ref('')
const selectedEventType = ref('')
const topicFilter = ref('')
const loading = ref(false)
const running = ref(false)
const detailLoading = ref(false)
const errorMessage = ref('')

const profileOptions = ['production_current', 'evidence_first_v2']

const currentDataset = computed(() =>
  datasets.value.find((dataset) => dataset.dataset === selectedDataset.value),
)

const eventTypeOptions = computed(() => currentDataset.value?.event_types ?? [])

const latestRun = computed(() => selectedRun.value ?? runs.value[0] ?? null)

const formatPercent = (value: number | undefined) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return `${Math.round(value * 100)}%`
}

const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return '--'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString('zh-CN', { hour12: false })
}

const metricCards = computed(() => {
  const run = latestRun.value
  const preferredProfile =
    selectedProfile.value || (run?.profiles.includes('evidence_first_v2') ? 'evidence_first_v2' : run?.profiles[0])
  const metrics = preferredProfile ? run?.summary.metric_breakdown[preferredProfile] : undefined
  return [
    { key: 'citation', label: '引用完整率', value: metrics?.citation_completeness },
    { key: 'evidence', label: '证据覆盖率', value: metrics?.evidence_coverage },
    { key: 'risk', label: '风险提示覆盖率', value: metrics?.risk_notice_coverage },
    { key: 'stability', label: '结论稳定性', value: metrics?.conclusion_stability },
    { key: 'failure', label: '失败率', value: metrics?.failure_rate },
  ]
})

const formatMetricLine = (metrics?: EvaluationMetricBreakdown) => {
  if (!metrics) {
    return '暂无指标'
  }
  return (
  `引用 ${formatPercent(metrics.citation_completeness)} / 证据 ${formatPercent(
    metrics.evidence_coverage,
  )} / 风险 ${formatPercent(metrics.risk_notice_coverage)} / 稳定 ${formatPercent(
    metrics.conclusion_stability,
  )} / 失败 ${formatPercent(metrics.failure_rate)}`
  )
}

const loadDatasets = async () => {
  if (!authStore.accessToken) {
    return
  }
  datasets.value = await adminApi.listEvaluationDatasets(authStore.accessToken)
  if (!datasets.value.some((dataset) => dataset.dataset === selectedDataset.value)) {
    selectedDataset.value = datasets.value[0]?.dataset ?? 'default_research_cases'
  }
}

const loadRuns = async () => {
  if (!authStore.accessToken) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    runs.value = await adminApi.listEvaluationRuns(authStore.accessToken, {
      dataset: selectedDataset.value || undefined,
      promptProfile: selectedProfile.value || undefined,
      eventType: selectedEventType.value || undefined,
      topic: topicFilter.value || undefined,
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '评估运行加载失败'
    runs.value = []
  } finally {
    loading.value = false
  }
}

const runEvaluation = async () => {
  if (!authStore.accessToken) {
    return
  }
  running.value = true
  errorMessage.value = ''
  try {
    // 关键流程：固定双 profile 对比，确保后台页始终能直接展示新旧口径差异。
    selectedRun.value = await adminApi.createEvaluationRun(authStore.accessToken, {
      dataset: selectedDataset.value,
      profiles: profileOptions,
    })
    await loadRuns()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '评估运行失败'
  } finally {
    running.value = false
  }
}

const applyFilters = async () => {
  selectedRun.value = null
  await loadRuns()
}

const openRun = async (runId: string) => {
  if (!authStore.accessToken) {
    return
  }
  detailLoading.value = true
  try {
    selectedRun.value = await adminApi.getEvaluationRun(authStore.accessToken, runId)
  } finally {
    detailLoading.value = false
  }
}

const groupedCaseResults = computed(() => {
  const run = selectedRun.value
  if (!run) {
    return []
  }
  const groups = new Map<string, EvaluationCaseResult[]>()
  for (const result of run.case_results) {
    const rows = groups.get(result.case_id) ?? []
    rows.push(result)
    groups.set(result.case_id, rows)
  }
  return Array.from(groups.entries()).flatMap(([caseId, results]) => {
    const primary = results[0]
    if (!primary) {
      return []
    }
    return [{ caseId, results, primary }]
  })
})

onMounted(async () => {
  await loadDatasets()
  await loadRuns()
})
</script>

<template>
  <section class="admin-evaluations-page">
    <header class="evaluations-header">
      <div>
        <p class="panel-kicker">PROMPT EVAL</p>
        <h1>研究评估中心</h1>
        <p class="section-note">固定评估集对比 production_current 与 evidence_first_v2，验证证据优先和谨慎结论是否改善。</p>
      </div>
      <el-button
        type="primary"
        :loading="running"
        data-testid="evaluation-run"
        @click="runEvaluation"
      >
        运行评估
      </el-button>
    </header>

    <section class="dataset-panel">
      <div>
        <span class="panel-label">当前数据集</span>
        <strong>{{ currentDataset?.title || selectedDataset }}</strong>
        <p>{{ currentDataset?.case_count ?? 0 }} 条案例 · {{ currentDataset?.event_types.join(' / ') }}</p>
      </div>
      <select v-model="selectedDataset">
        <option v-for="dataset in datasets" :key="dataset.dataset" :value="dataset.dataset">
          {{ dataset.title }}
        </option>
      </select>
    </section>

    <section class="filter-panel">
      <label class="filter-item">
        <span>Prompt Profile</span>
        <select v-model="selectedProfile" data-testid="evaluation-filter-profile">
          <option value="">全部</option>
          <option v-for="profile in profileOptions" :key="profile" :value="profile">{{ profile }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>事件类型</span>
        <select v-model="selectedEventType" data-testid="evaluation-filter-event-type">
          <option value="">全部</option>
          <option v-for="eventType in eventTypeOptions" :key="eventType" :value="eventType">{{ eventType }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>主题</span>
        <input v-model.trim="topicFilter" data-testid="evaluation-filter-topic" />
      </label>
      <el-button
        type="primary"
        :loading="loading"
        data-testid="evaluation-apply-filters"
        @click="applyFilters"
      >
        筛选
      </el-button>
    </section>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    />

    <section class="metric-grid">
      <article v-for="metric in metricCards" :key="metric.key" class="metric-card">
        <span>{{ metric.label }}</span>
        <strong>{{ formatPercent(metric.value) }}</strong>
      </article>
    </section>

    <section class="evaluations-content">
      <el-card class="runs-card" shadow="never">
        <template #header>
          <div class="card-header">
            <h2>评估运行</h2>
            <span>{{ runs.length }} 次</span>
          </div>
        </template>
        <el-skeleton v-if="loading" :rows="5" animated />
        <el-empty v-else-if="runs.length === 0" description="暂无评估运行记录" />
        <button
          v-for="run in runs"
          v-else
          :key="run.run_id"
          type="button"
          class="run-row"
          data-testid="evaluation-run-row"
          @click="openRun(run.run_id)"
        >
          <div class="run-row__head">
            <strong>{{ run.run_id }}</strong>
            <span :data-status="run.status">{{ run.status }}</span>
          </div>
          <p>{{ run.dataset }} · {{ (run.profiles || []).join(' / ') }}</p>
          <p>{{ formatDateTime(run.completed_at || run.started_at) }}</p>
        </button>
      </el-card>

      <el-card class="detail-card" shadow="never">
        <template #header>
          <div class="card-header">
            <h2>Profile 对比</h2>
          </div>
        </template>
        <el-skeleton v-if="detailLoading" :rows="5" animated />
        <el-empty v-else-if="!selectedRun" description="运行或选择一次评估查看详情" />
        <div v-else class="run-detail">
          <div class="profile-grid">
            <article
              v-for="profile in selectedRun.profiles"
              :key="profile"
              class="profile-card"
            >
              <h3>{{ profile }}</h3>
              <p>{{ formatMetricLine(selectedRun.summary.metric_breakdown[profile]) }}</p>
            </article>
          </div>

          <div class="case-list">
            <article v-for="group in groupedCaseResults" :key="group.caseId" class="case-card">
              <div class="case-card__head">
                <strong>{{ group.caseId }}</strong>
                <span>{{ group.primary.event_type }}</span>
              </div>
              <p>{{ group.primary.ts_code }} · {{ group.primary.topic }}</p>
              <div class="tag-row">
                <span v-for="tag in group.primary.case_tags" :key="tag">{{ tag }}</span>
              </div>
              <div class="profile-result" v-for="result in group.results" :key="result.prompt_profile">
                <h4>{{ result.prompt_profile }}</h4>
                <p>{{ result.conclusion }}</p>
                <p>证据：{{ result.evidence_kinds.join(' / ') || '--' }}</p>
                <p>风险：{{ result.risk_notices.join(' / ') || '--' }}</p>
              </div>
            </article>
          </div>
        </div>
      </el-card>
    </section>
  </section>
</template>

<style scoped>
.admin-evaluations-page {
  display: grid;
  gap: 1rem;
}

.evaluations-header,
.dataset-panel,
.filter-panel,
.metric-card,
.run-row,
.case-card,
.profile-card {
  border: 1px solid var(--terminal-border);
  border-radius: 8px;
  background: var(--terminal-card-elevated-bg);
}

.evaluations-header,
.dataset-panel,
.filter-panel {
  padding: 1rem 1.1rem;
}

.evaluations-header,
.dataset-panel,
.card-header,
.run-row__head,
.case-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.panel-kicker,
.panel-label {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: #f7b500;
  letter-spacing: 0.12em;
  font-size: 0.74rem;
  text-transform: uppercase;
}

h1,
h2,
h3,
h4,
p {
  margin: 0;
}

.section-note,
.dataset-panel p,
.run-row p,
.case-card p,
.profile-card p {
  color: var(--terminal-muted);
  line-height: 1.45;
}

.dataset-panel select,
.filter-item input,
.filter-item select {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid color-mix(in srgb, var(--terminal-primary) 18%, var(--terminal-border));
  border-radius: 8px;
  padding: 0.6rem 0.7rem;
  background: var(--terminal-input-bg);
  color: var(--terminal-text);
}

.filter-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  align-items: end;
  gap: 0.8rem;
}

.filter-item {
  display: grid;
  gap: 0.4rem;
}

.filter-item span {
  color: var(--terminal-muted);
  font-size: 0.82rem;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.8rem;
}

.metric-card {
  padding: 0.85rem 0.95rem;
  display: grid;
  gap: 0.35rem;
}

.metric-card span {
  color: var(--terminal-muted);
  font-size: 0.82rem;
}

.metric-card strong {
  font-size: 1.35rem;
}

.evaluations-content {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(0, 1.6fr);
  gap: 1rem;
  align-items: start;
}

.runs-card,
.detail-card {
  border-radius: 8px;
  background: var(--terminal-card-bg);
}

.run-row {
  width: 100%;
  text-align: left;
  color: var(--terminal-text);
  padding: 0.85rem;
  display: grid;
  gap: 0.35rem;
  cursor: pointer;
}

.run-row + .run-row {
  margin-top: 0.65rem;
}

.run-row:hover {
  border-color: color-mix(in srgb, var(--terminal-primary) 42%, var(--terminal-border));
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.profile-card,
.case-card {
  padding: 0.85rem;
  display: grid;
  gap: 0.55rem;
}

.case-list {
  display: grid;
  gap: 0.8rem;
  margin-top: 1rem;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.tag-row span {
  border: 1px solid var(--terminal-border);
  border-radius: 999px;
  padding: 0.18rem 0.48rem;
  color: var(--terminal-muted);
  font-size: 0.78rem;
}

.profile-result {
  border-top: 1px solid var(--terminal-border);
  padding-top: 0.55rem;
  display: grid;
  gap: 0.3rem;
}

@media (max-width: 980px) {
  .filter-panel,
  .metric-grid,
  .evaluations-content,
  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
