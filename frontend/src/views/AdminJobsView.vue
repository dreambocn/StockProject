<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  adminApi,
  type AdminJobDetail,
  type AdminJobListItem,
  type AdminJobSummary,
} from '../api/admin'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const loading = ref(false)
const summaryLoading = ref(false)
const detailLoading = ref(false)
const errorMessage = ref('')
const items = ref<AdminJobListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const summary = ref<AdminJobSummary | null>(null)
const selectedDetail = ref<AdminJobDetail | null>(null)

const filters = ref({
  jobType: '',
  status: '',
  triggerSource: '',
  resourceKey: '',
})

const recent24hCount = computed(() => {
  const now = Date.now()
  return items.value.filter((item) => {
    if (!item.created_at) {
      return false
    }
    const createdAt = new Date(item.created_at).getTime()
    return Number.isFinite(createdAt) && now - createdAt <= 24 * 60 * 60 * 1000
  }).length
})

const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return '--'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString('zh-CN', {
    hour12: false,
  })
}

const formatDuration = (value: number | null | undefined) => {
  if (typeof value !== 'number') {
    return '--'
  }
  if (value < 1000) {
    return `${value} ms`
  }
  return `${(value / 1000).toFixed(1)} s`
}

const loadSummary = async () => {
  if (!authStore.accessToken) {
    return
  }
  summaryLoading.value = true
  try {
    summary.value = await adminApi.getJobSummary(authStore.accessToken)
  } finally {
    summaryLoading.value = false
  }
}

const loadJobs = async () => {
  if (!authStore.accessToken) {
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const payload = await adminApi.listJobs(authStore.accessToken, {
      jobType: filters.value.jobType || undefined,
      status: filters.value.status || undefined,
      triggerSource: filters.value.triggerSource || undefined,
      resourceKey: filters.value.resourceKey || undefined,
      page: page.value,
      pageSize: pageSize.value,
    })
    items.value = payload.items
    total.value = payload.total
    page.value = payload.page
    pageSize.value = payload.page_size
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '任务列表加载失败'
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

const refreshPage = async () => {
  await Promise.all([loadSummary(), loadJobs()])
}

const applyFilters = async () => {
  page.value = 1
  await loadJobs()
}

const openDetail = async (jobId: string) => {
  if (!authStore.accessToken) {
    return
  }
  detailLoading.value = true
  try {
    selectedDetail.value = await adminApi.getJobDetail(authStore.accessToken, jobId)
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  await refreshPage()
})
</script>

<template>
  <section class="admin-jobs-page">
    <header class="jobs-header">
      <div>
        <p class="panel-kicker">TASK OPS</p>
        <h1>后台任务中心</h1>
        <p class="section-note">统一查看分析、新闻、自选与股票同步任务的执行状态。</p>
      </div>
      <el-button :loading="loading || summaryLoading" @click="refreshPage">刷新</el-button>
    </header>

    <section class="summary-grid" data-testid="admin-jobs-summary">
      <article class="summary-card">
        <span>总任务数</span>
        <strong>{{ summaryLoading ? '--' : summary?.total ?? total }}</strong>
      </article>
      <article class="summary-card">
        <span>运行中</span>
        <strong>{{ summaryLoading ? '--' : summary?.status_counts?.running ?? 0 }}</strong>
      </article>
      <article class="summary-card">
        <span>失败数</span>
        <strong>{{ summaryLoading ? '--' : summary?.status_counts?.failed ?? 0 }}</strong>
      </article>
      <article class="summary-card">
        <span>最近 24h</span>
        <strong>{{ loading ? '--' : recent24hCount }}</strong>
      </article>
    </section>

    <section class="filter-panel">
      <div class="filter-grid">
        <label class="filter-item">
          <span>任务类型</span>
          <input v-model.trim="filters.jobType" data-testid="admin-jobs-filter-job-type" />
        </label>
        <label class="filter-item">
          <span>状态</span>
          <select v-model="filters.status" data-testid="admin-jobs-filter-status">
            <option value="">全部</option>
            <option value="queued">queued</option>
            <option value="running">running</option>
            <option value="success">success</option>
            <option value="partial">partial</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <label class="filter-item">
          <span>触发来源</span>
          <input v-model.trim="filters.triggerSource" data-testid="admin-jobs-filter-trigger-source" />
        </label>
        <label class="filter-item">
          <span>资源关键字</span>
          <input v-model.trim="filters.resourceKey" data-testid="admin-jobs-filter-resource-key" />
        </label>
      </div>
      <div class="filter-actions">
        <el-button type="primary" @click="applyFilters">筛选</el-button>
      </div>
    </section>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    />

    <section class="jobs-content">
      <el-card class="jobs-list-card" shadow="never">
        <template #header>
          <div class="jobs-list-header">
            <h2>任务列表</h2>
            <span>共 {{ total }} 条</span>
          </div>
        </template>

        <el-skeleton v-if="loading" :rows="6" animated />
        <el-empty v-else-if="items.length === 0" description="暂无任务记录" />
        <div v-else class="jobs-list" data-testid="admin-jobs-list">
          <button
            v-for="item in items"
            :key="item.id"
            type="button"
            class="job-row"
            @click="openDetail(item.id)"
          >
            <div class="job-row__head">
              <strong>{{ item.job_type }}</strong>
              <span class="job-status" :data-status="item.status">{{ item.status }}</span>
            </div>
            <p class="job-row__meta">
              {{ item.trigger_source }} · {{ item.resource_key || '--' }} ·
              {{ formatDateTime(item.started_at || item.created_at) }}
            </p>
            <p class="job-row__summary">{{ item.summary || '暂无摘要' }}</p>
          </button>
        </div>
      </el-card>

      <el-card class="jobs-detail-card" shadow="never">
        <template #header>
          <div class="jobs-list-header">
            <h2>任务详情</h2>
          </div>
        </template>
        <el-skeleton v-if="detailLoading" :rows="5" animated />
        <el-empty v-else-if="!selectedDetail" description="点击左侧任务查看详情" />
        <div v-else class="job-detail" data-testid="admin-job-detail">
          <div class="job-detail__meta">
            <span>任务类型：{{ selectedDetail.job_type }}</span>
            <span>状态：{{ selectedDetail.status }}</span>
            <span>耗时：{{ formatDuration(selectedDetail.duration_ms) }}</span>
            <span>开始时间：{{ formatDateTime(selectedDetail.started_at) }}</span>
            <span>结束时间：{{ formatDateTime(selectedDetail.finished_at) }}</span>
          </div>
          <div class="job-detail__block">
            <h3>关联实体</h3>
            <p>
              {{ selectedDetail.linked_entity.entity_type || '--' }} /
              {{ selectedDetail.linked_entity.entity_id || '--' }}
            </p>
          </div>
          <div class="job-detail__block">
            <h3>错误信息</h3>
            <p>{{ selectedDetail.error_type || '--' }}</p>
            <p>{{ selectedDetail.error_message || '--' }}</p>
          </div>
          <div class="job-detail__block">
            <h3>Metrics</h3>
            <pre>{{ JSON.stringify(selectedDetail.metrics_json ?? {}, null, 2) }}</pre>
          </div>
          <div class="job-detail__block">
            <h3>Payload</h3>
            <pre>{{ JSON.stringify(selectedDetail.payload_json ?? {}, null, 2) }}</pre>
          </div>
        </div>
      </el-card>
    </section>
  </section>
</template>

<style scoped>
.admin-jobs-page {
  display: grid;
  gap: 1rem;
}

.jobs-header,
.filter-panel,
.summary-card,
.job-row {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: var(--terminal-card-elevated-bg);
}

.jobs-header,
.filter-panel {
  padding: 1rem 1.1rem;
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: #f7b500;
  letter-spacing: 0.14em;
  font-size: 0.74rem;
  text-transform: uppercase;
}

.section-note {
  margin: 0.2rem 0 0;
  color: var(--terminal-muted);
}

.jobs-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.8rem;
}

.summary-card {
  padding: 0.9rem 1rem;
  display: grid;
  gap: 0.4rem;
}

.summary-card span {
  color: var(--terminal-muted);
  font-size: 0.84rem;
}

.summary-card strong {
  font-size: 1.4rem;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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

.filter-item input,
.filter-item select {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid color-mix(in srgb, var(--terminal-primary) 18%, var(--terminal-border));
  border-radius: 10px;
  padding: 0.6rem 0.7rem;
  background: var(--terminal-input-bg);
  color: var(--terminal-text);
}

.filter-actions {
  margin-top: 0.8rem;
  display: flex;
  justify-content: flex-end;
}

.jobs-content {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
  gap: 1rem;
}

.jobs-list-card,
.jobs-detail-card {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: var(--terminal-card-strong-bg);
}

.jobs-list-header {
  display: flex;
  justify-content: space-between;
  gap: 0.6rem;
  align-items: center;
}

.jobs-list {
  display: grid;
  gap: 0.7rem;
}

.job-row {
  padding: 0.85rem 0.95rem;
  color: var(--terminal-text);
  text-align: left;
  cursor: pointer;
}

.job-row__head {
  display: flex;
  justify-content: space-between;
  gap: 0.6rem;
  align-items: center;
}

.job-row__meta,
.job-row__summary,
.job-detail__meta {
  color: var(--terminal-muted);
  font-size: 0.84rem;
}

.job-row__meta,
.job-row__summary {
  margin: 0.35rem 0 0;
}

.job-status {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  border: 1px solid rgba(123, 197, 255, 0.18);
}

.job-status[data-status='success'] {
  color: #9ff4c2;
}

.job-status[data-status='failed'] {
  color: #ff9b9b;
}

.job-status[data-status='running'] {
  color: #ffd58a;
}

.job-detail {
  display: grid;
  gap: 0.9rem;
}

.job-detail__meta {
  display: grid;
  gap: 0.25rem;
}

.job-detail__block {
  display: grid;
  gap: 0.35rem;
}

.job-detail__block h3,
.jobs-list-header h2 {
  margin: 0;
}

.job-detail__block p,
.job-detail__block pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.job-detail__block pre {
  padding: 0.75rem;
  border-radius: 12px;
  background: var(--terminal-code-bg);
  border: 1px solid rgba(123, 197, 255, 0.1);
  color: var(--terminal-code-text);
}

@media (max-width: 960px) {
  .summary-grid,
  .filter-grid,
  .jobs-content {
    grid-template-columns: 1fr;
  }
}
</style>
