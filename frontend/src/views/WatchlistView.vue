<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { watchlistApi, type WatchlistItemResponse } from '../api/watchlist'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const loading = ref(false)
const items = ref<WatchlistItemResponse[]>([])
const updatingKeys = ref<string[]>([])

const isUpdating = computed(() => (tsCode: string, field: string) =>
  updatingKeys.value.includes(`${tsCode}:${field}`),
)

const loadWatchlist = async () => {
  if (!authStore.accessToken) {
    items.value = []
    return
  }

  loading.value = true
  try {
    const payload = await watchlistApi.getWatchlist(authStore.accessToken)
    items.value = payload.items
  } finally {
    loading.value = false
  }
}

const openAnalysis = async (tsCode: string) => {
  await router.push({
    path: '/analysis',
    query: { ts_code: tsCode, source: 'watchlist' },
  })
}

const removeItem = async (tsCode: string) => {
  if (!authStore.accessToken) {
    return
  }
  await watchlistApi.deleteWatchlistItem(authStore.accessToken, tsCode)
  await loadWatchlist()
}

const updateItemSwitch = async (
  item: WatchlistItemResponse,
  field: 'hourly_sync_enabled' | 'daily_analysis_enabled' | 'web_search_enabled',
  value: boolean,
) => {
  if (!authStore.accessToken) {
    return
  }

  const updateKey = `${item.ts_code}:${field}`
  updatingKeys.value = [...updatingKeys.value, updateKey]
  try {
    // 关键流程：开关更新直接走局部 PATCH，成功后只替换当前卡片，避免整页刷新打断用户操作。
    const updated = await watchlistApi.updateWatchlistItem(
      authStore.accessToken,
      item.ts_code,
      { [field]: value },
    )
    items.value = items.value.map((current) =>
      current.ts_code === item.ts_code ? updated : current,
    )
  } finally {
    updatingKeys.value = updatingKeys.value.filter((key) => key !== updateKey)
  }
}

onMounted(() => {
  void loadWatchlist()
})
</script>

<template>
  <section class="watchlist-page">
    <header class="watchlist-header">
      <div>
        <h1>{{ t('watchlist.title') }}</h1>
        <p class="watchlist-subtitle">{{ t('watchlist.subtitle') }}</p>
      </div>
      <el-button :loading="loading" @click="loadWatchlist">{{ t('home.refresh') }}</el-button>
    </header>

    <el-empty v-if="!loading && items.length === 0" :description="t('watchlist.empty')" />

    <div v-else class="watchlist-grid">
      <el-card
        v-for="item in items"
        :key="item.id"
        class="watchlist-card"
        shadow="never"
      >
        <div class="watchlist-card__header">
          <div>
            <h2>{{ item.instrument?.name ?? item.ts_code }}</h2>
            <p class="watchlist-card__code">{{ item.ts_code }}</p>
          </div>
          <div class="watchlist-card__actions">
            <el-button type="primary" @click="openAnalysis(item.ts_code)">
              {{ t('watchlist.openAnalysis') }}
            </el-button>
            <el-button plain @click="removeItem(item.ts_code)">
              {{ t('watchlist.remove') }}
            </el-button>
          </div>
        </div>

        <div class="watchlist-card__meta">
          <button
            :data-testid="`watchlist-hourly-sync-${item.ts_code}`"
            type="button"
            class="watchlist-toggle"
            :disabled="isUpdating(item.ts_code, 'hourly_sync_enabled')"
            @click="updateItemSwitch(item, 'hourly_sync_enabled', !item.hourly_sync_enabled)"
          >
            {{ t('watchlist.hourlySync') }}：{{ item.hourly_sync_enabled ? 'ON' : 'OFF' }}
          </button>
          <button
            :data-testid="`watchlist-daily-analysis-${item.ts_code}`"
            type="button"
            class="watchlist-toggle"
            :disabled="isUpdating(item.ts_code, 'daily_analysis_enabled')"
            @click="updateItemSwitch(item, 'daily_analysis_enabled', !item.daily_analysis_enabled)"
          >
            {{ t('watchlist.dailyAnalysis') }}：{{ item.daily_analysis_enabled ? 'ON' : 'OFF' }}
          </button>
          <button
            :data-testid="`watchlist-web-search-${item.ts_code}`"
            type="button"
            class="watchlist-toggle"
            :disabled="isUpdating(item.ts_code, 'web_search_enabled')"
            @click="updateItemSwitch(item, 'web_search_enabled', !item.web_search_enabled)"
          >
            {{ t('watchlist.webSearch') }}：{{ item.web_search_enabled ? 'ON' : 'OFF' }}
          </button>
        </div>

        <div class="watchlist-card__dates">
          <p>{{ t('watchlist.latestSync') }}：{{ item.last_hourly_sync_at ?? '--' }}</p>
          <p>{{ t('watchlist.latestAnalysis') }}：{{ item.last_daily_analysis_at ?? '--' }}</p>
        </div>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.watchlist-page {
  display: grid;
  gap: 1rem;
}

.watchlist-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.watchlist-header h1 {
  margin: 0;
}

.watchlist-subtitle {
  margin: 0.3rem 0 0;
  color: var(--terminal-muted);
}

.watchlist-grid {
  display: grid;
  gap: 0.85rem;
}

.watchlist-card {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(19, 29, 48, 0.95), rgba(11, 18, 32, 0.96));
}

.watchlist-card__header,
.watchlist-card__meta {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  flex-wrap: wrap;
}

.watchlist-card__code,
.watchlist-card__dates p,
.watchlist-card__meta span {
  color: var(--terminal-muted);
  font-size: 0.84rem;
}

.watchlist-toggle {
  border: 1px solid var(--terminal-border);
  border-radius: 999px;
  padding: 0.35rem 0.75rem;
  background: rgba(8, 14, 25, 0.7);
  color: var(--terminal-muted);
  cursor: pointer;
  transition: 0.2s ease;
}

.watchlist-toggle:hover:not(:disabled) {
  color: #f5fbff;
  border-color: rgba(123, 197, 255, 0.3);
}

.watchlist-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.watchlist-card__actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.watchlist-card__dates {
  margin-top: 0.8rem;
  display: grid;
  gap: 0.2rem;
}

.watchlist-card__dates p {
  margin: 0;
}

@media (max-width: 760px) {
  .watchlist-header,
  .watchlist-card__header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
