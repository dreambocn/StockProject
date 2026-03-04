<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { ApiError } from '../api/http'
import { stocksApi, type StockDailySnapshot, type StockDetail } from '../api/stocks'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const loading = ref(false)
const errorMessage = ref('')
const detail = ref<StockDetail | null>(null)
const dailyRows = ref<StockDailySnapshot[]>([])

const tsCode = computed(() => String(route.params.tsCode ?? '').trim().toUpperCase())

const formatNumber = (value: number | null, digits = 2) => {
  if (value === null) {
    return '--'
  }
  return value.toFixed(digits)
}

const formatPercent = (value: number | null) => {
  if (value === null) {
    return '--'
  }
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

const loadData = async () => {
  if (!tsCode.value) {
    errorMessage.value = t('errors.fallback')
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    // 关键流程：详情与日线并行加载，减少二次渲染等待时间并保持页面状态一致。
    const [detailPayload, dailyPayload] = await Promise.all([
      stocksApi.getStockDetail(tsCode.value),
      stocksApi.getStockDaily(tsCode.value, 60),
    ])
    detail.value = detailPayload
    dailyRows.value = dailyPayload
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    loading.value = false
  }
}

const goBack = async () => {
  await router.push('/')
}

onMounted(async () => {
  await loadData()
})
</script>

<template>
  <section class="detail-page" v-motion :initial="{ opacity: 0, y: 18 }" :enter="{ opacity: 1, y: 0 }">
    <el-card class="detail-card" shadow="never">
      <div class="title-row">
        <div>
          <p class="panel-kicker">{{ t('stockDetail.kicker') }}</p>
          <h1>{{ detail?.instrument.name ?? tsCode }}</h1>
          <p class="code-line">{{ detail?.instrument.ts_code ?? tsCode }}</p>
        </div>
        <el-button text @click="goBack">{{ t('stockDetail.back') }}</el-button>
      </div>

      <el-alert v-if="errorMessage" class="detail-alert" :title="errorMessage" type="error" :closable="false" show-icon />

      <div v-if="detail" class="metrics-grid">
        <div class="metric-item">
          <span class="metric-label">{{ t('stockDetail.latestClose') }}</span>
          <strong>{{ formatNumber(detail.latest_snapshot?.close ?? null) }}</strong>
        </div>
        <div class="metric-item">
          <span class="metric-label">{{ t('stockDetail.latestChange') }}</span>
          <strong>{{ formatPercent(detail.latest_snapshot?.pct_chg ?? null) }}</strong>
        </div>
        <div class="metric-item">
          <span class="metric-label">{{ t('stockDetail.industry') }}</span>
          <strong>{{ detail.instrument.industry ?? '--' }}</strong>
        </div>
        <div class="metric-item">
          <span class="metric-label">{{ t('stockDetail.exchange') }}</span>
          <strong>{{ detail.instrument.exchange ?? '--' }}</strong>
        </div>
      </div>
    </el-card>

    <el-card class="detail-card" shadow="never">
      <div class="daily-header">
        <h2>{{ t('stockDetail.dailyTitle') }}</h2>
        <el-button :loading="loading" @click="loadData">{{ t('home.refresh') }}</el-button>
      </div>

      <el-empty v-if="!loading && dailyRows.length === 0" :description="t('stockDetail.empty')" />

      <el-table v-else :data="dailyRows" class="daily-table" size="small">
        <el-table-column prop="trade_date" label="Date" min-width="120" />
        <el-table-column prop="open" label="Open" min-width="100" />
        <el-table-column prop="high" label="High" min-width="100" />
        <el-table-column prop="low" label="Low" min-width="100" />
        <el-table-column prop="close" label="Close" min-width="100" />
        <el-table-column prop="pct_chg" label="%Chg" min-width="100" />
      </el-table>
    </el-card>
  </section>
</template>

<style scoped>
.detail-page {
  display: grid;
  gap: 1rem;
}

.detail-card {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(19, 29, 48, 0.95), rgba(11, 18, 32, 0.96));
}

.title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.9rem;
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: var(--terminal-primary);
  letter-spacing: 0.12em;
  font-size: 0.76rem;
  text-transform: uppercase;
}

h1 {
  margin: 0.45rem 0 0.2rem;
}

.code-line {
  margin: 0;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
}

.detail-alert {
  margin-top: 0.8rem;
}

.metrics-grid {
  margin-top: 1rem;
  display: grid;
  gap: 0.7rem;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.metric-item {
  border: 1px solid var(--terminal-border);
  border-radius: 10px;
  padding: 0.6rem;
  display: grid;
  gap: 0.3rem;
  background: color-mix(in srgb, var(--terminal-surface, #10172a) 90%, transparent);
}

.metric-label {
  color: var(--terminal-muted);
  font-size: 0.78rem;
}

.daily-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.8rem;
}

h2 {
  margin: 0;
}

.daily-table {
  width: 100%;
}

@media (max-width: 760px) {
  .title-row,
  .daily-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
