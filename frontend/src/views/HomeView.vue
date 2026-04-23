<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '../api/http'
import { stocksApi, type StockListItem } from '../api/stocks'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const loadingMore = ref(false)
const keyword = ref('')
const stocks = ref<StockListItem[]>([])
const errorMessage = ref('')
const hasMore = ref(true)
const page = ref(1)
const pageSize = 20
const quotePatchByTsCode = ref<
  Record<
    string,
    {
      close: number | null
      pctChg: number | null
      tradeDate: string | null
    }
  >
>({})
const loadMoreTrigger = ref<HTMLElement | null>(null)
const intersectionObserver = ref<IntersectionObserver | null>(null)
const scheduledLoadFrame = ref<number | null>(null)

const formatPrice = (value: number | null | undefined) => {
  if (value === null || value === undefined) {
    return '--'
  }
  return value.toFixed(2)
}

const formatTradeDate = (value: string | null | undefined) => {
  if (!value) {
    return '--'
  }
  const normalized = value.replace(/-/g, '')
  if (normalized.length !== 8) {
    return value
  }
  return `${normalized.slice(0, 4)}-${normalized.slice(4, 6)}-${normalized.slice(6, 8)}`
}

const formatChange = (value: number | null | undefined) => {
  if (value === null || value === undefined) {
    return '--'
  }
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

const resolveTagType = (value: number | null | undefined) => {
  if (value === null || value === undefined) {
    return 'info'
  }
  return value >= 0 ? 'success' : 'danger'
}

const resolveSubtitle = (fullname: string | null | undefined, tsCode: string) => {
  const normalized = fullname?.trim()
  return normalized && normalized.length > 0 ? normalized : tsCode
}

const resolveQuoteField = (stock: StockListItem) => {
  const patched = quotePatchByTsCode.value[stock.ts_code]
  return {
    close: patched?.close ?? stock.close,
    pctChg: patched?.pctChg ?? stock.pct_chg,
    tradeDate: patched?.tradeDate ?? stock.trade_date,
  }
}

const backfillMissingCardQuotes = async (items: StockListItem[]) => {
  const missingCodes = items
    .filter((item) => {
      const hasLocalPatch = quotePatchByTsCode.value[item.ts_code]
      if (hasLocalPatch) {
        return false
      }
      return item.close === null || item.trade_date === null
    })
    .map((item) => item.ts_code)

  if (missingCodes.length === 0) {
    return
  }

  // 关键边界：分批并发补拉，避免触底时集中请求导致接口被瞬时打满。
  const concurrency = 5
  for (let index = 0; index < missingCodes.length; index += concurrency) {
    const chunk = missingCodes.slice(index, index + concurrency)
    await Promise.all(
      chunk.map(async (tsCode) => {
        try {
          // 关键流程：仅对首页缺失价格/日期的卡片补拉最近一条日线，避免全量逐卡请求。
          const rows = await stocksApi.getStockDaily(tsCode, {
            limit: 1,
            period: 'daily',
          })
          const latest = rows[0]
          if (!latest) {
            return
          }
          quotePatchByTsCode.value = {
            ...quotePatchByTsCode.value,
            [tsCode]: {
              close: latest.close,
              pctChg: latest.pct_chg,
              tradeDate: latest.trade_date,
            },
          }
        } catch {
          return
        }
      }),
    )
  }
}

const mergeStocksByTsCode = (existing: StockListItem[], incoming: StockListItem[], reset: boolean) => {
  const merged = reset ? [] : [...existing]
  const seen = new Set(merged.map((item) => item.ts_code))
  let appendedCount = 0

  // 关键流程：分页合并按 ts_code 去重，避免后端排序变化导致重复卡片占位。
  for (const item of incoming) {
    if (seen.has(item.ts_code)) {
      continue
    }
    seen.add(item.ts_code)
    merged.push(item)
    appendedCount += 1
  }

  return {
    merged,
    appendedCount,
  }
}

const loadStocksPage = async (reset: boolean) => {
  if (reset) {
    // 关键流程：重置搜索时清空分页与补丁缓存，确保结果和关键字一致。
    page.value = 1
    hasMore.value = true
    loading.value = true
    quotePatchByTsCode.value = {}
  } else {
    // 关键状态边界：触底加载时必须受 hasMore/loading 双条件保护，避免重复请求和并发翻页。
    if (!hasMore.value || loading.value || loadingMore.value) {
      return
    }
    loadingMore.value = true
  }

  errorMessage.value = ''
  try {
    // 关键流程：首页查询统一走分页接口；reset=true 时替换数据，触底时追加数据。
    const pageItems = await stocksApi.listStocks(
      keyword.value.trim() || undefined,
      undefined,
      page.value,
      pageSize,
    )

    const mergeResult = mergeStocksByTsCode(stocks.value, pageItems, reset)
    stocks.value = mergeResult.merged
    await backfillMissingCardQuotes(pageItems)

    if (pageItems.length < pageSize) {
      hasMore.value = false
      return
    }

    // 关键边界：当下一页全部是重复 ts_code 时停止继续翻页，避免旧卡片被重复数据覆盖。
    if (!reset && mergeResult.appendedCount === 0) {
      hasMore.value = false
      return
    }

    page.value += 1
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    if (reset) {
      loading.value = false
    } else {
      loadingMore.value = false
    }
  }
}

const refreshStocks = async () => {
  await loadStocksPage(true)
}

const loadMoreStocks = async () => {
  await loadStocksPage(false)
}

const scheduleLoadMore = () => {
  if (scheduledLoadFrame.value !== null) {
    return
  }

  // 关键流程：触底事件在滚动中会高频触发，使用动画帧合并可减少抖动与重复调度。
  scheduledLoadFrame.value = window.requestAnimationFrame(() => {
    scheduledLoadFrame.value = null
    void loadMoreStocks()
  })
}

const goToHotNews = async () => {
  await router.push('/news/hot')
}

const setupLoadMoreObserver = () => {
  if (typeof IntersectionObserver === 'undefined') {
    return
  }
  if (!loadMoreTrigger.value) {
    return
  }

  intersectionObserver.value?.disconnect()
  intersectionObserver.value = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        scheduleLoadMore()
      }
    },
    {
      // 关键边界：提前触底预加载，避免用户滚动到底部时出现明显空窗。
      rootMargin: '0px 0px 260px 0px',
      threshold: 0.01,
    },
  )
  intersectionObserver.value.observe(loadMoreTrigger.value)
}

onMounted(async () => {
  await refreshStocks()
  await nextTick()
  setupLoadMoreObserver()
})

onUnmounted(() => {
  intersectionObserver.value?.disconnect()
  intersectionObserver.value = null
  if (scheduledLoadFrame.value !== null) {
    window.cancelAnimationFrame(scheduledLoadFrame.value)
    scheduledLoadFrame.value = null
  }
})
</script>

<template>
  <section class="terminal-page" v-motion :initial="{ opacity: 0, y: 16 }" :enter="{ opacity: 1, y: 0 }">
    <header class="section-header">
      <div>
        <p class="section-kicker">{{ t('home.kicker') }}</p>
        <h1>{{ t('home.title') }}</h1>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="goToHotNews">{{ t('home.hotNews') }}</el-button>
        <el-input
          v-model="keyword"
          class="search-input"
          clearable
          :placeholder="t('home.searchPlaceholder')"
          @keyup.enter="refreshStocks"
        />
        <el-button :loading="loading" @click="refreshStocks">{{ t('home.search') }}</el-button>
      </div>
    </header>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" :closable="false" show-icon />

    <el-empty v-if="!loading && stocks.length === 0" :description="t('home.empty')" />

    <div class="stock-waterfall">
      <div v-for="stock in stocks" :key="stock.ts_code" class="stock-waterfall-item">
        <router-link class="card-link" :to="`/stocks/${stock.ts_code}`">
          <el-card class="terminal-card" shadow="never">
            <div class="stock-card-vertical">
              <div class="stock-head">
                <strong>{{ stock.symbol }}</strong>
                <el-tag :type="resolveTagType(resolveQuoteField(stock).pctChg)">
                  {{ formatChange(resolveQuoteField(stock).pctChg) }}
                </el-tag>
              </div>
              <p class="stock-name">{{ stock.name }}</p>
              <p class="stock-code">{{ resolveSubtitle(stock.fullname, stock.ts_code) }}</p>
              <p class="stock-price">¥{{ formatPrice(resolveQuoteField(stock).close) }}</p>
              <p class="stock-date">{{ formatTradeDate(resolveQuoteField(stock).tradeDate) }}</p>
            </div>
          </el-card>
        </router-link>
      </div>
    </div>

    <div ref="loadMoreTrigger" data-testid="load-more-trigger" class="load-more-trigger">
      <span v-if="loadingMore">{{ t('home.loadingMore') }}</span>
      <span v-else-if="!hasMore && stocks.length > 0">{{ t('home.noMore') }}</span>
    </div>
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.search-input {
  min-width: 220px;
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
  background: var(--terminal-card-muted-bg);
  box-shadow: var(--terminal-shadow);
}

.stock-waterfall {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
}

.stock-waterfall-item {
  min-width: 0;
}

.card-link {
  display: block;
  text-decoration: none;
}

.stock-card-vertical {
  display: grid;
  gap: 0.14rem;
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

.stock-code,
.stock-date {
  margin: 0.1rem 0;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.82rem;
}

.stock-price {
  margin: 0.4rem 0 0;
  font-size: 1.3rem;
  font-family: 'IBM Plex Mono', monospace;
}

.load-more-trigger {
  min-height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.78rem;
  letter-spacing: 0.06em;
}

@media (max-width: 760px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    width: 100%;
  }

  .search-input {
    flex: 1;
    min-width: 0;
  }

  .stock-waterfall {
    grid-template-columns: 1fr;
  }

}

@media (min-width: 761px) and (max-width: 1090px) {
  .stock-waterfall {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
