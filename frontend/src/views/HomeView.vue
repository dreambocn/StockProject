<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

type Stock = {
  symbol: string
  name: string
  price: number
  change: number
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const { t } = useI18n()
const loading = ref(false)
const stocks = ref<Stock[]>([
  // 首屏提供降级占位数据，避免接口波动时页面完全空白。
  { symbol: 'AAPL', name: 'Apple', price: 213.48, change: 1.42 },
  { symbol: 'TSLA', name: 'Tesla', price: 256.74, change: -0.95 },
  { symbol: 'NVDA', name: 'NVIDIA', price: 917.32, change: 2.16 },
])

const refreshStocks = async () => {
  loading.value = true
  try {
    const response = await fetch(`${apiBaseUrl}/api/stocks`)
    if (!response.ok) {
      // 请求失败时保留当前数据，不打断页面主流程。
      return
    }

    const payload = await response.json()
    if (Array.isArray(payload) && payload.length > 0) {
      // 仅在拿到有效列表时更新，避免异常 payload 覆盖现有数据。
      stocks.value = payload as Stock[]
    }
  } catch {
    return
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refreshStocks()
})
</script>

<template>
  <section class="terminal-page" v-motion :initial="{ opacity: 0, y: 16 }" :enter="{ opacity: 1, y: 0 }">
    <header class="section-header">
      <div>
        <p class="section-kicker">{{ t('home.kicker') }}</p>
        <h1>{{ t('home.title') }}</h1>
      </div>
      <el-button type="primary" :loading="loading" @click="refreshStocks">{{ t('home.refresh') }}</el-button>
    </header>

    <el-row :gutter="14">
      <el-col v-for="stock in stocks" :key="stock.symbol" :xs="24" :sm="12" :md="8">
        <el-card class="terminal-card" shadow="never">
          <div class="stock-head">
            <strong>{{ stock.symbol }}</strong>
            <el-tag :type="stock.change >= 0 ? 'success' : 'danger'">
              {{ stock.change >= 0 ? '+' : '' }}{{ stock.change.toFixed(2) }}%
            </el-tag>
          </div>
          <p class="stock-name">{{ stock.name }}</p>
          <p class="stock-price">${{ stock.price.toFixed(2) }}</p>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>

<style scoped>
.terminal-page {
  display: grid;
  gap: 0.95rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
}

.section-kicker {
  margin: 0 0 0.3rem;
  color: var(--terminal-muted);
  letter-spacing: 0.1em;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.78rem;
}

h1 {
  margin: 0;
  font-size: clamp(1.6rem, 3vw, 2.2rem);
}

.terminal-card {
  border: 1px solid var(--terminal-border);
  border-radius: 14px;
  background: linear-gradient(140deg, rgba(26, 38, 59, 0.96), rgba(14, 23, 37, 0.92));
}

.stock-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stock-name {
  margin: 0.72rem 0 0.25rem;
  color: var(--terminal-muted);
}

.stock-price {
  margin: 0;
  font-size: 1.3rem;
  font-family: 'IBM Plex Mono', monospace;
}

@media (max-width: 760px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
