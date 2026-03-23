<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { ApiError } from '../api/http'
import {
  stocksApi,
  type StockAdjFactor,
  type StockDailySnapshot,
  type StockDetail,
  type StockRelatedNewsItem,
} from '../api/stocks'

type KlinePeriod = 'daily' | 'weekly' | 'monthly'
type AdjustMode = 'none' | 'qfq' | 'hfq'

type KlineRow = {
  tsCode: string
  tradeDateKey: string
  tradeDateLabel: string
  open: number
  high: number
  low: number
  close: number
  preClose: number | null
  change: number | null
  pctChg: number | null
  vol: number | null
  amount: number | null
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const loading = ref(false)
const relatedNewsLoading = ref(false)
const errorMessage = ref('')
const detail = ref<StockDetail | null>(null)
const dailyRows = ref<StockDailySnapshot[]>([])
const relatedNews = ref<StockRelatedNewsItem[]>([])
const showAllNews = ref(false)
const adjFactors = ref<StockAdjFactor[]>([])
const selectedPeriod = ref<KlinePeriod>('daily')
const selectedAdjustMode = ref<AdjustMode>('none')
const hoveredIndex = ref<number | null>(null)

const chartWidth = 980
const chartHeight = 520
const chartPaddingX = 42
const panelGap = 14
const pricePanelTop = 24
const pricePanelHeight = 250
const volumePanelTop = pricePanelTop + pricePanelHeight + panelGap
const volumePanelHeight = 95
const rsiPanelTop = volumePanelTop + volumePanelHeight + panelGap
const rsiPanelHeight = 80

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

const formatCompactNumber = (value: number | null) => {
  if (value === null) {
    return '--'
  }
  if (value >= 100000000) {
    return `${(value / 100000000).toFixed(2)}亿`
  }
  if (value >= 10000) {
    return `${(value / 10000).toFixed(2)}万`
  }
  return value.toFixed(0)
}

const toTradeDateKey = (value: string) => value.replace(/-/g, '').slice(0, 8)

const toTradeDateLabel = (value: string) => {
  const key = toTradeDateKey(value)
  if (key.length !== 8) {
    return value
  }
  return `${key.slice(0, 4)}-${key.slice(4, 6)}-${key.slice(6, 8)}`
}

const toDate = (tradeDateKey: string) => {
  const year = Number(tradeDateKey.slice(0, 4))
  const month = Number(tradeDateKey.slice(4, 6))
  const day = Number(tradeDateKey.slice(6, 8))
  return new Date(year, month - 1, day)
}

const getWeekKey = (tradeDateKey: string) => {
  const dateValue = toDate(tradeDateKey)
  const day = dateValue.getDay() || 7
  dateValue.setDate(dateValue.getDate() + 4 - day)
  const yearStart = new Date(dateValue.getFullYear(), 0, 1)
  const week = Math.ceil(((dateValue.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${dateValue.getFullYear()}-W${String(week).padStart(2, '0')}`
}

const aggregateRows = (rows: KlineRow[], period: KlinePeriod): KlineRow[] => {
  if (period === 'daily') {
    return rows
  }

  const grouped = new Map<string, KlineRow[]>()
  for (const item of rows) {
    const key = period === 'weekly' ? getWeekKey(item.tradeDateKey) : item.tradeDateKey.slice(0, 6)
    if (!grouped.has(key)) {
      grouped.set(key, [])
    }
    grouped.get(key)?.push(item)
  }

  const result: KlineRow[] = []
  const orderedKeys = Array.from(grouped.keys()).sort()
  for (const key of orderedKeys) {
    const bucket = grouped.get(key)
    if (!bucket || bucket.length === 0) {
      continue
    }
    const sortedBucket = bucket.slice().sort((a, b) => a.tradeDateKey.localeCompare(b.tradeDateKey))
    const first = sortedBucket[0]
    const last = sortedBucket[sortedBucket.length - 1]
    if (!first || !last) {
      continue
    }
    let high = first.high
    let low = first.low
    let vol = 0
    let amount = 0
    sortedBucket.forEach((row) => {
      high = Math.max(high, row.high)
      low = Math.min(low, row.low)
      vol += row.vol ?? 0
      amount += row.amount ?? 0
    })

    result.push({
      tsCode: first.tsCode,
      tradeDateKey: last.tradeDateKey,
      tradeDateLabel: last.tradeDateLabel,
      open: first.open,
      high,
      low,
      close: last.close,
      preClose: first.preClose,
      change: null,
      pctChg: null,
      vol,
      amount,
    })
  }

  for (let index = 0; index < result.length; index += 1) {
    const current = result[index]
    if (!current) {
      continue
    }
    const prevClose = index === 0 ? current.preClose : result[index - 1]?.close ?? current.preClose
    if (prevClose === null || prevClose === 0) {
      current.change = null
      current.pctChg = null
      continue
    }
    const change = current.close - prevClose
    current.change = change
    current.pctChg = (change / prevClose) * 100
  }

  return result
}

const rawBaseRows = computed(() => {
  const mapped = dailyRows.value
    .map((item) => {
      const open = item.open
      const high = item.high
      const low = item.low
      const close = item.close
      if (open === null || high === null || low === null || close === null) {
        return null
      }

      const tradeDateKey = toTradeDateKey(item.trade_date)
      if (tradeDateKey.length !== 8) {
        return null
      }

      return {
        tsCode: item.ts_code,
        tradeDateKey,
        tradeDateLabel: toTradeDateLabel(tradeDateKey),
        open,
        high,
        low,
        close,
        preClose: item.pre_close,
        change: item.change,
        pctChg: item.pct_chg,
        vol: item.vol,
        amount: item.amount,
      } as KlineRow
    })
    .filter((item): item is KlineRow => item !== null)

  return mapped.sort((a, b) => a.tradeDateKey.localeCompare(b.tradeDateKey))
})

const factorByTradeDateKey = computed(() => {
  const map = new Map<string, number>()
  adjFactors.value.forEach((item) => {
    const key = toTradeDateKey(item.trade_date)
    if (key.length !== 8 || !Number.isFinite(item.adj_factor) || item.adj_factor <= 0) {
      return
    }
    map.set(key, item.adj_factor)
  })
  return map
})

const adjustedRows = computed(() => {
  const mode = selectedAdjustMode.value
  if (mode === 'none') {
    return rawBaseRows.value
  }

  const factors = factorByTradeDateKey.value
  const rows = rawBaseRows.value
  if (rows.length === 0 || factors.size === 0) {
    return rows
  }

  const latestFactor = factors.get(rows[rows.length - 1]?.tradeDateKey ?? '')
  const firstFactor = factors.get(rows[0]?.tradeDateKey ?? '')
  const baseFactor = mode === 'qfq' ? latestFactor : firstFactor
  if (!baseFactor || baseFactor <= 0) {
    return rows
  }

  return rows.map((item) => {
    const currentFactor = factors.get(item.tradeDateKey)
    if (!currentFactor || currentFactor <= 0) {
      return item
    }
    const ratio = currentFactor / baseFactor
    return {
      ...item,
      open: item.open * ratio,
      high: item.high * ratio,
      low: item.low * ratio,
      close: item.close * ratio,
      preClose: item.preClose === null ? null : item.preClose * ratio,
      change: item.change === null ? null : item.change * ratio,
    }
  })
})

const baseRows = computed(() => adjustedRows.value)

const klineRows = computed(() => aggregateRows(baseRows.value, selectedPeriod.value))

const chartStats = computed(() => {
  if (klineRows.value.length === 0) {
    return {
      minPrice: 0,
      maxPrice: 1,
      minRsi: 0,
      maxRsi: 100,
      maxVol: 1,
      firstDate: '--',
      lastDate: '--',
    }
  }

  const highs = klineRows.value.map((item) => item.high)
  const lows = klineRows.value.map((item) => item.low)
  const vols = klineRows.value.map((item) => item.vol ?? 0)
  const maxPrice = Math.max(...highs)
  const minPrice = Math.min(...lows)
  const padding = Math.max((maxPrice - minPrice) * 0.06, 0.01)

  return {
    minPrice: minPrice - padding,
    maxPrice: maxPrice + padding,
    minRsi: 0,
    maxRsi: 100,
    maxVol: Math.max(...vols, 1),
    firstDate: klineRows.value[0]?.tradeDateLabel ?? '--',
    lastDate: klineRows.value[klineRows.value.length - 1]?.tradeDateLabel ?? '--',
  }
})

const calcMa = (values: number[], period: number) => {
  const result: number[] = []
  for (let i = 0; i < values.length; i += 1) {
    const start = Math.max(0, i - period + 1)
    const windowValues = values.slice(start, i + 1)
    const sum = windowValues.reduce((acc, value) => acc + value, 0)
    result.push(sum / windowValues.length)
  }
  return result
}

const calcRsi = (values: number[], period: number) => {
  const result: Array<number | null> = new Array(values.length).fill(null)
  if (values.length <= period) {
    return result
  }

  for (let i = period; i < values.length; i += 1) {
    let gains = 0
    let losses = 0
    for (let j = i - period + 1; j <= i; j += 1) {
      const current = values[j] ?? 0
      const previous = values[j - 1] ?? current
      const diff = current - previous
      if (diff >= 0) {
        gains += diff
      } else {
        losses += Math.abs(diff)
      }
    }
    const avgGain = gains / period
    const avgLoss = losses / period
    if (avgLoss === 0) {
      result[i] = 100
      continue
    }
    const rs = avgGain / avgLoss
    result[i] = 100 - 100 / (1 + rs)
  }

  return result
}

const closes = computed(() => klineRows.value.map((item) => item.close))
const ma5 = computed(() => calcMa(closes.value, 5))
const ma10 = computed(() => calcMa(closes.value, 10))
const ma20 = computed(() => calcMa(closes.value, 20))
const ma60 = computed(() => calcMa(closes.value, 60))
const rsi6 = computed(() => calcRsi(closes.value, 6))
const rsi12 = computed(() => calcRsi(closes.value, 12))
const rsi24 = computed(() => calcRsi(closes.value, 24))

const drawWidth = computed(() => chartWidth - chartPaddingX * 2)
const xStep = computed(() =>
  klineRows.value.length > 1 ? drawWidth.value / (klineRows.value.length - 1) : 0,
)
const candleWidth = computed(() => Math.max(4, Math.min(14, xStep.value * 0.62)))

const xAt = (index: number) => chartPaddingX + xStep.value * index

const priceToY = (value: number) => {
  const span = chartStats.value.maxPrice - chartStats.value.minPrice
  const ratio = span <= 0 ? 0 : (value - chartStats.value.minPrice) / span
  return pricePanelTop + pricePanelHeight - ratio * pricePanelHeight
}

const volumeToY = (value: number) => {
  const ratio = value / chartStats.value.maxVol
  return volumePanelTop + volumePanelHeight - ratio * volumePanelHeight
}

const rsiToY = (value: number) => {
  const ratio = (value - chartStats.value.minRsi) / (chartStats.value.maxRsi - chartStats.value.minRsi)
  return rsiPanelTop + rsiPanelHeight - ratio * rsiPanelHeight
}

const maPoints = (values: number[]) =>
  values.map((value, index) => `${xAt(index).toFixed(2)},${priceToY(value).toFixed(2)}`).join(' ')

const rsiPoints = (values: Array<number | null>) =>
  values
    .map((value, index) => {
      if (value === null) {
        return null
      }
      return `${xAt(index).toFixed(2)},${rsiToY(value).toFixed(2)}`
    })
    .filter((item): item is string => item !== null)
    .join(' ')

const hoveredRow = computed(() => {
  if (hoveredIndex.value === null) {
    return null
  }
  return klineRows.value[hoveredIndex.value] ?? null
})

const activeRow = computed(() => {
  if (hoveredRow.value) {
    return hoveredRow.value
  }
  return klineRows.value[klineRows.value.length - 1] ?? null
})

const activeClose = computed(() => activeRow.value?.close ?? detail.value?.latest_snapshot?.close ?? null)
const activePctChg = computed(() => activeRow.value?.pctChg ?? detail.value?.latest_snapshot?.pct_chg ?? null)

const activeHoverX = computed(() => {
  if (hoveredIndex.value === null) {
    return null
  }
  return xAt(hoveredIndex.value)
})

const activeHoverY = computed(() => {
  if (!hoveredRow.value) {
    return null
  }
  return priceToY(hoveredRow.value.close)
})

const activeTooltipLeft = computed(() => {
  if (activeHoverX.value === null) {
    return '50%'
  }
  return `${(activeHoverX.value / chartWidth) * 100}%`
})

const newsPreviewLimit = 6
const displayedNews = computed(() => {
  if (showAllNews.value) {
    return relatedNews.value
  }
  return relatedNews.value.slice(0, newsPreviewLimit)
})

const hasMoreNews = computed(() => relatedNews.value.length > newsPreviewLimit)

const updateHoveredPoint = (event: MouseEvent) => {
  if (klineRows.value.length === 0) {
    hoveredIndex.value = null
    return
  }

  const currentTarget = event.currentTarget as SVGRectElement | null
  if (!currentTarget) {
    hoveredIndex.value = klineRows.value.length - 1
    return
  }

  const bounds = currentTarget.getBoundingClientRect()
  if (bounds.width <= 0) {
    hoveredIndex.value = klineRows.value.length - 1
    return
  }

  const normalizedOffset = (event.clientX - bounds.left) / bounds.width
  const clampedOffset = Math.max(0, Math.min(1, normalizedOffset))
  const nearestIndex = Math.round(clampedOffset * (klineRows.value.length - 1))

  // 关键状态流转：交互层仅更新本地高亮索引，不触发请求，避免鼠标移动导致额外 API 压力。
  hoveredIndex.value = nearestIndex
}

const clearHoveredPoint = () => {
  hoveredIndex.value = null
}

const selectPeriod = (period: KlinePeriod) => {
  if (selectedPeriod.value === period) {
    return
  }
  selectedPeriod.value = period
  hoveredIndex.value = null
  // 关键流程：周期切换必须触发后端真实请求，优先走数据库命中，缺失再由后端回源补齐。
  void loadCoreData()
}

const selectAdjustMode = (mode: AdjustMode) => {
  if (selectedAdjustMode.value === mode) {
    return
  }
  // 关键状态流转：复权模式只在前端改写展示价格，不改变后端原始行情数据。
  selectedAdjustMode.value = mode
  hoveredIndex.value = null
}

const loadAdjFactors = async (rows: StockDailySnapshot[]) => {
  if (!tsCode.value || rows.length === 0) {
    adjFactors.value = []
    return
  }

  const sortedKeys = rows
    .map((item) => toTradeDateKey(item.trade_date))
    .filter((key) => key.length === 8)
    .sort()

  if (sortedKeys.length === 0) {
    adjFactors.value = []
    return
  }

  const startDate = sortedKeys[0]
  const endDate = sortedKeys[sortedKeys.length - 1]
  try {
    const payload = await stocksApi.getStockAdjFactor(tsCode.value, {
      limit: Math.max(rows.length, 120),
      startDate,
      endDate,
    })
    adjFactors.value = payload
  } catch {
    // 降级分支：复权因子失败时保持原始价格展示，避免详情页整体不可用。
    adjFactors.value = []
    selectedAdjustMode.value = 'none'
  }
}

const loadRelatedNews = async () => {
  if (!tsCode.value) {
    relatedNews.value = []
    return
  }

  relatedNewsLoading.value = true
  try {
    // 关键流程：资讯加载与K线主链路拆开执行，避免资讯接口波动拖慢核心看板首屏。
    relatedNews.value = await stocksApi.getStockRelatedNews(tsCode.value, 50)
    showAllNews.value = false
  } catch {
    // 降级分支：资讯拉取失败时展示空态，不影响主看板核心行情与指标继续可用。
    relatedNews.value = []
  } finally {
    relatedNewsLoading.value = false
  }
}

const loadCoreData = async () => {
  if (!tsCode.value) {
    // 关键边界：缺少 tsCode 时不发请求，直接进入错误提示分支，避免无效接口调用。
    errorMessage.value = t('errors.fallback')
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    // 关键流程：优先并行拉取详情和K线，先稳定主看板；复权因子按时间窗二次请求。
    const [detailPayload, dailyPayload] = await Promise.all([
      stocksApi.getStockDetail(tsCode.value),
      stocksApi.getStockDaily(tsCode.value, {
        limit: 60,
        period: selectedPeriod.value,
      }),
    ])
    detail.value = detailPayload
    dailyRows.value = dailyPayload
    // 关键状态流转：复权因子依赖已拉取的行情时间窗，必须在 dailyRows 更新后再请求。
    await loadAdjFactors(dailyPayload)
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

watch(
  () => dailyRows.value,
  () => {
    hoveredIndex.value = null
  },
)

const loadData = async () => {
  await loadCoreData()
  await loadRelatedNews()
}

const goBack = async () => {
  await router.push('/')
}

const goToAnalysis = async () => {
  if (!tsCode.value) {
    return
  }

  await router.push({
    path: '/analysis',
    query: {
      ts_code: tsCode.value,
      source: 'stock_detail',
    },
  })
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
          <p data-testid="stock-fullname" class="fullname-line">
            {{ detail?.instrument.fullname ?? '--' }}
          </p>
        </div>
        <div class="title-actions">
          <el-button
            type="primary"
            plain
            data-testid="stock-analysis-entry"
            @click="goToAnalysis"
          >
            {{ t('analysisWorkbench.enterButton') }}
          </el-button>
          <el-button text @click="goBack">{{ t('stockDetail.back') }}</el-button>
        </div>
      </div>

      <el-alert v-if="errorMessage" class="detail-alert" :title="errorMessage" type="error" :closable="false" show-icon />

      <div v-if="detail" class="metrics-grid">
        <div class="metric-item">
          <span class="metric-label">{{ t('stockDetail.latestClose') }}</span>
          <strong data-testid="latest-close-value">{{ formatNumber(activeClose) }}</strong>
        </div>
        <div class="metric-item">
          <span class="metric-label">{{ t('stockDetail.latestChange') }}</span>
          <strong data-testid="latest-change-value">{{ formatPercent(activePctChg) }}</strong>
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

    <section class="content-grid">
      <el-card data-testid="stock-detail-main-panel" class="detail-card" shadow="never">
      <div class="daily-header">
        <h2>{{ t('stockDetail.dailyTitle') }}</h2>
        <div class="daily-actions">
          <el-button-group class="action-group">
            <el-button
              data-testid="kline-period-daily"
              :type="selectedPeriod === 'daily' ? 'primary' : 'default'"
              @click="selectPeriod('daily')"
            >
              {{ t('stockDetail.kline.periodDaily') }}
            </el-button>
            <el-button
              data-testid="kline-period-weekly"
              :type="selectedPeriod === 'weekly' ? 'primary' : 'default'"
              @click="selectPeriod('weekly')"
            >
              {{ t('stockDetail.kline.periodWeekly') }}
            </el-button>
            <el-button
              data-testid="kline-period-monthly"
              :type="selectedPeriod === 'monthly' ? 'primary' : 'default'"
              @click="selectPeriod('monthly')"
            >
              {{ t('stockDetail.kline.periodMonthly') }}
            </el-button>
          </el-button-group>
          <el-button-group class="action-group">
            <el-button
              data-testid="kline-adjust-none"
              :type="selectedAdjustMode === 'none' ? 'primary' : 'default'"
              @click="selectAdjustMode('none')"
            >
              {{ t('stockDetail.kline.adjustNone') }}
            </el-button>
            <el-button
              data-testid="kline-adjust-qfq"
              :type="selectedAdjustMode === 'qfq' ? 'primary' : 'default'"
              @click="selectAdjustMode('qfq')"
            >
              {{ t('stockDetail.kline.adjustQfq') }}
            </el-button>
            <el-button
              data-testid="kline-adjust-hfq"
              :type="selectedAdjustMode === 'hfq' ? 'primary' : 'default'"
              @click="selectAdjustMode('hfq')"
            >
              {{ t('stockDetail.kline.adjustHfq') }}
            </el-button>
          </el-button-group>
          <el-button class="action-refresh" :loading="loading" @click="loadData">{{ t('home.refresh') }}</el-button>
        </div>
      </div>

      <el-empty v-if="!loading && klineRows.length === 0" :description="t('stockDetail.empty')" />

      <div
        v-else
        data-testid="kline-chart"
        class="kline-panel"
        v-motion
        :initial="{ opacity: 0, y: 12 }"
        :enter="{ opacity: 1, y: 0 }"
      >
        <div class="kline-meta-row">
          <div class="ma-legend">
            <span>MA5: {{ formatNumber(ma5[ma5.length - 1] ?? null) }}</span>
            <span>MA10: {{ formatNumber(ma10[ma10.length - 1] ?? null) }}</span>
            <span>MA20: {{ formatNumber(ma20[ma20.length - 1] ?? null) }}</span>
            <span>MA60: {{ formatNumber(ma60[ma60.length - 1] ?? null) }}</span>
          </div>
          <p class="trend-window">
            {{ chartStats.firstDate }} → {{ chartStats.lastDate }}
            <span class="adjust-badge">{{ selectedAdjustMode === 'none' ? t('stockDetail.kline.adjustRaw') : selectedAdjustMode.toUpperCase() }}</span>
          </p>
        </div>

        <div class="chart-wrap">
          <svg class="kline-svg" :viewBox="`0 0 ${chartWidth} ${chartHeight}`" role="img" aria-label="kline chart">
            <defs>
              <linearGradient id="klineAreaGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="rgba(123, 197, 255, 0.16)" />
                <stop offset="100%" stop-color="rgba(123, 197, 255, 0.02)" />
              </linearGradient>
            </defs>

            <rect :x="chartPaddingX" :y="pricePanelTop" :width="drawWidth" :height="pricePanelHeight" class="panel-bg" />
            <rect :x="chartPaddingX" :y="volumePanelTop" :width="drawWidth" :height="volumePanelHeight" class="panel-bg" />
            <rect :x="chartPaddingX" :y="rsiPanelTop" :width="drawWidth" :height="rsiPanelHeight" class="panel-bg" />

            <line :x1="chartPaddingX" :x2="chartWidth - chartPaddingX" :y1="pricePanelTop" :y2="pricePanelTop" class="axis-line" />
            <line
              :x1="chartPaddingX"
              :x2="chartWidth - chartPaddingX"
              :y1="pricePanelTop + pricePanelHeight"
              :y2="pricePanelTop + pricePanelHeight"
              class="axis-line"
            />
            <line
              :x1="chartPaddingX"
              :x2="chartWidth - chartPaddingX"
              :y1="volumePanelTop + volumePanelHeight"
              :y2="volumePanelTop + volumePanelHeight"
              class="axis-line"
            />
            <line :x1="chartPaddingX" :x2="chartWidth - chartPaddingX" :y1="rsiPanelTop" :y2="rsiPanelTop" class="axis-line" />
            <line
              :x1="chartPaddingX"
              :x2="chartWidth - chartPaddingX"
              :y1="rsiPanelTop + rsiPanelHeight"
              :y2="rsiPanelTop + rsiPanelHeight"
              class="axis-line"
            />

            <line
              v-for="(row, index) in klineRows"
              :key="`wick-${row.tradeDateKey}`"
              :x1="xAt(index)"
              :x2="xAt(index)"
              :y1="priceToY(row.high)"
              :y2="priceToY(row.low)"
              class="wick-line"
              :class="row.close >= row.open ? 'up' : 'down'"
            />

            <rect
              v-for="(row, index) in klineRows"
              :key="`body-${row.tradeDateKey}`"
              :x="xAt(index) - candleWidth / 2"
              :y="Math.min(priceToY(row.open), priceToY(row.close))"
              :width="candleWidth"
              :height="Math.max(Math.abs(priceToY(row.close) - priceToY(row.open)), 1.4)"
              class="candle-body"
              :class="row.close >= row.open ? 'up' : 'down'"
            />

            <polyline :points="maPoints(ma5)" class="ma-line ma5" />
            <polyline :points="maPoints(ma10)" class="ma-line ma10" />
            <polyline :points="maPoints(ma20)" class="ma-line ma20" />
            <polyline :points="maPoints(ma60)" class="ma-line ma60" />

            <rect
              v-for="(row, index) in klineRows"
              :key="`vol-${row.tradeDateKey}`"
              :x="xAt(index) - candleWidth / 2"
              :y="volumeToY(row.vol ?? 0)"
              :width="candleWidth"
              :height="volumePanelTop + volumePanelHeight - volumeToY(row.vol ?? 0)"
              class="volume-bar"
              :class="row.close >= row.open ? 'up' : 'down'"
            />

            <polyline :points="rsiPoints(rsi6)" class="rsi-line rsi6" />
            <polyline :points="rsiPoints(rsi12)" class="rsi-line rsi12" />
            <polyline :points="rsiPoints(rsi24)" class="rsi-line rsi24" />

            <line
              v-if="activeHoverX !== null"
              :x1="activeHoverX"
              :x2="activeHoverX"
              :y1="pricePanelTop"
              :y2="rsiPanelTop + rsiPanelHeight"
              class="crosshair-line"
            />
            <line
              v-if="activeHoverY !== null"
              :x1="chartPaddingX"
              :x2="chartWidth - chartPaddingX"
              :y1="activeHoverY"
              :y2="activeHoverY"
              class="crosshair-line"
            />
            <circle v-if="activeHoverX !== null && activeHoverY !== null" :cx="activeHoverX" :cy="activeHoverY" r="5" class="active-dot" />

            <rect
              data-testid="kline-interaction-layer"
              :x="chartPaddingX"
              :y="pricePanelTop"
              :width="drawWidth"
              :height="rsiPanelTop + rsiPanelHeight - pricePanelTop"
              class="interaction-layer"
              @mousemove="updateHoveredPoint"
              @mouseleave="clearHoveredPoint"
            />
          </svg>

          <div v-if="hoveredRow" data-testid="kline-tooltip" class="kline-tooltip" :style="{ left: activeTooltipLeft }">
            <p>{{ hoveredRow.tradeDateLabel }}</p>
            <div class="tooltip-grid">
              <span>{{ t('stockDetail.kline.tooltip.open') }}: {{ formatNumber(hoveredRow.open) }}</span>
              <span>{{ t('stockDetail.kline.tooltip.close') }}: {{ formatNumber(hoveredRow.close) }}</span>
              <span>{{ t('stockDetail.kline.tooltip.high') }}: {{ formatNumber(hoveredRow.high) }}</span>
              <span>{{ t('stockDetail.kline.tooltip.low') }}: {{ formatNumber(hoveredRow.low) }}</span>
              <span>{{ t('stockDetail.kline.tooltip.change') }}: {{ formatPercent(hoveredRow.pctChg) }}</span>
              <span>{{ t('stockDetail.kline.tooltip.volume') }}: {{ formatCompactNumber(hoveredRow.vol) }}</span>
              <span>{{ t('stockDetail.kline.tooltip.amount') }}: {{ formatCompactNumber(hoveredRow.amount) }}</span>
            </div>
            <strong>¥{{ formatNumber(hoveredRow.close) }}</strong>
          </div>
        </div>

        <div class="indicator-tabs">
          <span class="active">RSI</span>
          <span>KDJ</span>
          <span>MACD</span>
          <span>WR</span>
          <span>DMI</span>
          <span>BIAS</span>
          <span>OBV</span>
          <span>CCI</span>
          <span>ROC</span>
        </div>
      </div>
      </el-card>

      <el-card data-testid="stock-detail-news-panel" class="detail-card detail-card-news" shadow="never">
        <div class="related-news-header">
          <h2>{{ t('stockDetail.relatedNews') }}</h2>
          <el-button
            v-if="hasMoreNews"
            text
            size="small"
            class="news-toggle"
            @click="showAllNews = !showAllNews"
          >
            {{ showAllNews ? '收起' : '查看更多' }}
          </el-button>
        </div>
        <el-skeleton v-if="relatedNewsLoading" :rows="4" animated />
        <el-empty v-else-if="relatedNews.length === 0" :description="t('stockDetail.relatedNewsEmpty')" />
        <div v-else class="related-news-list">
          <article
            v-for="item in displayedNews"
            :key="`${item.source}-${item.url ?? item.title}-${item.published_at ?? ''}`"
            class="related-news-item"
          >
            <p class="related-news-meta">{{ item.publisher ?? item.source }} · {{ item.published_at ?? '--' }}</p>
            <a
              v-if="item.url"
              class="related-news-link"
              :href="item.url"
              target="_blank"
              rel="noreferrer noopener"
            >
              {{ item.title }}
            </a>
            <p v-else class="related-news-title">{{ item.title }}</p>
            <p v-if="item.summary" class="related-news-summary">{{ item.summary }}</p>
          </article>
        </div>
      </el-card>
    </section>
  </section>
</template>

<style scoped>
.detail-page {
  display: grid;
  gap: 1rem;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 1rem;
  align-items: start;
}

.content-grid > .detail-card {
  height: 100%;
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

.title-actions {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  justify-content: flex-end;
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

.fullname-line {
  margin: 0.22rem 0 0;
  font-size: 0.8rem;
  color: color-mix(in srgb, var(--terminal-muted) 72%, white 28%);
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
  gap: 0.8rem;
}

.related-news-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.8rem;
}

.news-toggle {
  color: var(--terminal-primary);
  font-family: 'IBM Plex Mono', monospace;
}

.detail-card-news {
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: 760px;
}

.related-news-list {
  display: grid;
  gap: 0.55rem;
  flex: 1;
  min-height: 0;
  max-height: 620px;
  overflow: auto;
  padding-right: 0.2rem;
}

.related-news-item {
  border: 1px solid var(--terminal-border);
  border-radius: 10px;
  padding: 0.5rem 0.56rem;
  background: color-mix(in srgb, var(--terminal-surface, #10172a) 90%, transparent);
}

.related-news-meta {
  margin: 0;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
}

.related-news-link,
.related-news-title {
  margin: 0.28rem 0 0;
  font-size: 0.9rem;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.related-news-link {
  color: var(--terminal-primary);
  text-decoration: none;
}

.related-news-summary {
  margin: 0.28rem 0 0;
  color: var(--terminal-muted);
  font-size: 0.8rem;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.daily-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  justify-content: flex-end;
  overflow: visible;
  scrollbar-width: thin;
  padding-bottom: 0.1rem;
}

.daily-actions :deep(.el-button) {
  white-space: nowrap;
}

.action-group,
.action-refresh {
  flex-shrink: 0;
}

.daily-header h2 {
  white-space: nowrap;
}

h2 {
  margin: 0;
}

.kline-panel {
  border: 1px solid rgba(123, 197, 255, 0.24);
  border-radius: 14px;
  padding: 0.75rem;
  background:
    radial-gradient(circle at 84% 10%, rgba(247, 181, 0, 0.12), transparent 44%),
    linear-gradient(145deg, rgba(10, 18, 32, 0.98), rgba(8, 14, 25, 0.97));
}

.kline-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.55rem;
  gap: 0.6rem;
}

.ma-legend {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
}

.ma-legend span:nth-child(1) {
  color: #57b8ff;
}

.ma-legend span:nth-child(2) {
  color: #f7b500;
}

.ma-legend span:nth-child(3) {
  color: #ec6ad8;
}

.ma-legend span:nth-child(4) {
  color: #6dd889;
}

.trend-window {
  margin: 0;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
}

.adjust-badge {
  margin-left: 0.35rem;
  color: #7bc5ff;
}

.chart-wrap {
  position: relative;
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(8, 14, 25, 0.84);
}

.kline-svg {
  width: 100%;
  display: block;
}

.panel-bg {
  fill: rgba(255, 255, 255, 0.02);
}

.axis-line {
  stroke: rgba(146, 161, 182, 0.35);
  stroke-width: 1;
}

.wick-line {
  stroke-width: 1;
}

.candle-body {
  rx: 1;
}

.wick-line.up,
.candle-body.up,
.volume-bar.up {
  stroke: #ff4d4f;
  fill: #ff4d4f;
}

.wick-line.down,
.candle-body.down,
.volume-bar.down {
  stroke: #12b76a;
  fill: #12b76a;
}

.ma-line,
.rsi-line {
  fill: none;
  stroke-width: 1.6;
}

.ma5 {
  stroke: #57b8ff;
}

.ma10 {
  stroke: #f7b500;
}

.ma20 {
  stroke: #ec6ad8;
}

.ma60 {
  stroke: #6dd889;
}

.rsi6 {
  stroke: #b7becd;
}

.rsi12 {
  stroke: #f7b500;
}

.rsi24 {
  stroke: #ec6ad8;
}

.crosshair-line {
  stroke: rgba(123, 197, 255, 0.48);
  stroke-width: 1;
  stroke-dasharray: 4 4;
}

.active-dot {
  fill: #7bc5ff;
  stroke: rgba(5, 12, 22, 0.95);
  stroke-width: 1.8;
}

.interaction-layer {
  fill: transparent;
  cursor: crosshair;
}

.kline-tooltip {
  position: absolute;
  top: 0.55rem;
  transform: translateX(-50%);
  border: 1px solid rgba(123, 197, 255, 0.42);
  border-radius: 10px;
  padding: 0.4rem 0.55rem;
  background: rgba(11, 19, 34, 0.96);
  pointer-events: none;
  box-shadow: 0 10px 24px rgba(2, 8, 18, 0.4);
  min-width: 160px;
}

.kline-tooltip p {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
  color: var(--terminal-muted);
}

.tooltip-grid {
  margin-top: 0.2rem;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.1rem 0.5rem;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
}

.kline-tooltip strong {
  display: block;
  margin-top: 0.22rem;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.9rem;
}

.indicator-tabs {
  margin-top: 0.45rem;
  border: 1px solid var(--terminal-border);
  border-radius: 8px;
  padding: 0.35rem 0.45rem;
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.7rem;
  color: var(--terminal-muted);
}

.indicator-tabs .active {
  color: #7bc5ff;
}

@media (max-width: 960px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .detail-card-news {
    position: static;
    display: block;
    max-height: 520px;
  }

  .related-news-list {
    flex: none;
    max-height: 420px;
    overflow: auto;
    padding-right: 0;
  }

  .daily-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .daily-actions {
    justify-content: flex-start;
  }

  .kline-meta-row {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 760px) {
  .title-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .title-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .daily-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
