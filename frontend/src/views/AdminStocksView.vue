<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { adminApi, type AdminStock } from '../api/admin'
import { ApiError } from '../api/http'
import { stocksApi, type StockTradeCalendar } from '../api/stocks'
import { useAuthStore } from '../stores/auth'
import { mapApiErrorMessage } from '../utils/apiErrorI18n'

const authStore = useAuthStore()
const { t } = useI18n()

const loadingStocks = ref(false)
const syncingStocks = ref(false)
const errorMessage = ref('')
const stocks = ref<AdminStock[]>([])
const tradeCalendarRows = ref<StockTradeCalendar[]>([])
const loadingTradeCalendar = ref(false)

const filters = reactive({
  keyword: '',
  listStatus: 'ALL',
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const tradeCalendarFilters = reactive({
  exchange: 'SSE',
  isOpen: '' as '' | '0' | '1',
  startDate: '',
  endDate: '',
})

const tradeCalendarPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const accessToken = computed(() => authStore.accessToken)

const totalStocks = computed(() => pagination.total)
const listedStocks = computed(() => stocks.value.filter((item) => item.list_status === 'L').length)
const delistedStocks = computed(() => stocks.value.filter((item) => item.list_status === 'D').length)

const pagedTradeCalendarRows = computed(() => {
  const start = (tradeCalendarPagination.page - 1) * tradeCalendarPagination.pageSize
  const end = start + tradeCalendarPagination.pageSize
  return tradeCalendarRows.value.slice(start, end)
})

const listStatusOptions = computed(() => [
  { label: t('adminStocks.filters.all'), value: 'ALL' },
  { label: t('adminStocks.filters.listed'), value: 'L' },
  { label: t('adminStocks.filters.delisted'), value: 'D' },
  { label: t('adminStocks.filters.paused'), value: 'P' },
  { label: t('adminStocks.filters.preListing'), value: 'G' },
])

const parameterPresets = computed(
  () =>
    [
      { testId: 'preset-all', label: t('adminStocks.filters.all'), value: 'ALL' },
      { testId: 'preset-l', label: 'L', value: 'L' },
      { testId: 'preset-d', label: 'D', value: 'D' },
      { testId: 'preset-p', label: 'P', value: 'P' },
      { testId: 'preset-g', label: 'G', value: 'G' },
    ] as const,
)

const formatDate = (value: string | null) => {
  if (!value) {
    return '--'
  }
  return value
}

const resolveListStatusTagType = (status: string) => {
  if (status === 'L') {
    return 'success'
  }
  if (status === 'D') {
    return 'danger'
  }
  return 'warning'
}

const resolveListStatusLabel = (status: string) => {
  if (status === 'L') {
    return t('adminStocks.status.listed')
  }
  if (status === 'D') {
    return t('adminStocks.status.delisted')
  }
  if (status === 'P') {
    return t('adminStocks.status.paused')
  }
  if (status === 'G') {
    return t('adminStocks.status.preListing')
  }
  return status
}

const applyListStatusPreset = (value: string) => {
  // 关键状态流转：参数按钮只负责切换查询参数，不直接触发请求，避免用户误触导致频繁刷新。
  filters.listStatus = value
}

const loadStocksFromDb = async () => {
  errorMessage.value = ''
  loadingStocks.value = true

  try {
    // 鉴权边界：后台股票查询必须携带管理员 access token，缺失时直接阻断请求。
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    // 关键流程：默认查询统一走数据库分页接口，避免每次刷新都触发外部源拉取。
    const response = await adminApi.listStocks(accessToken.value, {
      keyword: filters.keyword.trim() || undefined,
      listStatus: filters.listStatus,
      page: pagination.page,
      pageSize: pagination.pageSize,
    })
    stocks.value = response.items
    pagination.total = response.total
    pagination.page = response.page
    pagination.pageSize = response.page_size
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    loadingStocks.value = false
  }
}

const fetchWithParams = async () => {
  errorMessage.value = ''
  syncingStocks.value = true

  try {
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    // 关键副作用：按参数获取全量会触发服务端入库同步，完成后必须刷新数据库分页结果。
    await adminApi.fetchStocksFull(accessToken.value, {
      listStatus: filters.listStatus,
    })
    pagination.page = 1
    await loadStocksFromDb()
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    syncingStocks.value = false
  }
}

const defaultQuery = async () => {
  pagination.page = 1
  await loadStocksFromDb()
}

const queryTradeCalendar = async () => {
  loadingTradeCalendar.value = true
  try {
    // 关键流程：交易日历查询先走后端 DB-first 接口，管理员侧只做筛选参数透传。
    tradeCalendarRows.value = await stocksApi.getTradeCalendar({
      exchange: tradeCalendarFilters.exchange,
      isOpen: tradeCalendarFilters.isOpen || undefined,
      startDate: tradeCalendarFilters.startDate || undefined,
      endDate: tradeCalendarFilters.endDate || undefined,
    })
    tradeCalendarPagination.total = tradeCalendarRows.value.length
    tradeCalendarPagination.page = 1
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
    } else {
      errorMessage.value = t('errors.fallback')
    }
  } finally {
    loadingTradeCalendar.value = false
  }
}

const handleTradeCalendarPageChange = (page: number) => {
  tradeCalendarPagination.page = page
}

const handleTradeCalendarPageSizeChange = (pageSize: number) => {
  tradeCalendarPagination.pageSize = pageSize
  tradeCalendarPagination.page = 1
}

const handlePageChange = async (page: number) => {
  pagination.page = page
  await loadStocksFromDb()
}

const handlePageSizeChange = async (pageSize: number) => {
  pagination.pageSize = pageSize
  pagination.page = 1
  await loadStocksFromDb()
}

onMounted(async () => {
  await loadStocksFromDb()
})
</script>

<template>
  <section
    class="admin-page"
    v-motion
    :initial="{ opacity: 0, y: 18 }"
    :enter="{ opacity: 1, y: 0 }"
  >
    <header class="control-header">
      <div>
        <p class="panel-kicker">{{ t('adminStocks.kicker') }}</p>
        <h1>{{ t('adminStocks.title') }}</h1>
        <p class="section-note">{{ t('adminStocks.note') }}</p>
      </div>
      <div class="status-chips">
        <div class="status-chip">
          <span>{{ t('adminStocks.metrics.total') }}</span>
          <strong>{{ totalStocks }}</strong>
        </div>
        <div class="status-chip success">
          <span>{{ t('adminStocks.metrics.listed') }}</span>
          <strong>{{ listedStocks }}</strong>
        </div>
        <div class="status-chip danger">
          <span>{{ t('adminStocks.metrics.delisted') }}</span>
          <strong>{{ delistedStocks }}</strong>
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
      <div class="filters">
        <el-input
          v-model="filters.keyword"
          class="search-input"
          clearable
          :placeholder="t('adminStocks.filters.keywordPlaceholder')"
          @keyup.enter="defaultQuery"
        />
        <el-segmented v-model="filters.listStatus" :options="listStatusOptions" />
        <el-button data-testid="fetch-with-params" :loading="syncingStocks" @click="fetchWithParams">{{
          t('adminStocks.filters.fetchWithParams')
        }}</el-button>
        <el-button :loading="loadingStocks" @click="defaultQuery">{{
          t('adminStocks.filters.defaultQuery')
        }}</el-button>
      </div>

      <div class="parameter-bar">
        <span class="parameter-label">{{ t('adminStocks.filters.parameterLabel') }}</span>
        <el-button-group>
          <el-button
            v-for="preset in parameterPresets"
            :key="preset.value"
            :data-testid="preset.testId"
            :type="filters.listStatus === preset.value ? 'primary' : 'default'"
            @click="applyListStatusPreset(preset.value)"
          >
            {{ preset.label }}
          </el-button>
        </el-button-group>
      </div>

      <div class="table-shell">
        <el-table
          :data="stocks"
          v-loading="loadingStocks || syncingStocks"
          class="stocks-table theme-table"
          height="460"
          row-key="ts_code"
        >
          <el-table-column prop="ts_code" :label="t('adminStocks.table.tsCode')" min-width="130" />
          <el-table-column prop="symbol" :label="t('adminStocks.table.symbol')" min-width="110" />
          <el-table-column prop="name" :label="t('adminStocks.table.name')" min-width="150" />
          <el-table-column prop="industry" :label="t('adminStocks.table.industry')" min-width="140" />
          <el-table-column :label="t('adminStocks.table.listStatus')" min-width="120">
            <template #default="scope">
              <el-tag :type="resolveListStatusTagType(scope.row.list_status)">
                {{ resolveListStatusLabel(scope.row.list_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('adminStocks.table.listDate')" min-width="120">
            <template #default="scope">
              {{ formatDate(scope.row.list_date) }}
            </template>
          </el-table-column>
          <el-table-column :label="t('adminStocks.table.delistDate')" min-width="120">
            <template #default="scope">
              {{ formatDate(scope.row.delist_date) }}
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pagination-wrap">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="pagination.total"
          :current-page="pagination.page"
          :page-size="pagination.pageSize"
          :page-sizes="[20, 50, 100]"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>

      <div class="trade-cal-panel">
        <div class="trade-cal-header">
          <h3>{{ t('adminStocks.tradeCal.title') }}</h3>
          <el-button
            data-testid="trade-cal-query"
            :loading="loadingTradeCalendar"
            @click="queryTradeCalendar"
          >
            {{ t('adminStocks.tradeCal.query') }}
          </el-button>
        </div>

        <div class="trade-cal-filters">
          <el-select v-model="tradeCalendarFilters.exchange" class="trade-cal-field">
            <el-option label="SSE" value="SSE" />
            <el-option label="SZSE" value="SZSE" />
            <el-option label="BSE" value="BSE" />
          </el-select>
          <el-select v-model="tradeCalendarFilters.isOpen" class="trade-cal-field" clearable>
            <el-option :label="t('adminStocks.tradeCal.allStatus')" value="" />
            <el-option :label="t('adminStocks.tradeCal.openOnly')" value="1" />
            <el-option :label="t('adminStocks.tradeCal.closedOnly')" value="0" />
          </el-select>
          <el-date-picker
            v-model="tradeCalendarFilters.startDate"
            type="date"
            value-format="YYYYMMDD"
            :placeholder="t('adminStocks.tradeCal.startDate')"
            class="trade-cal-field"
          />
          <el-date-picker
            v-model="tradeCalendarFilters.endDate"
            type="date"
            value-format="YYYYMMDD"
            :placeholder="t('adminStocks.tradeCal.endDate')"
            class="trade-cal-field"
          />
        </div>

        <el-table
          :data="pagedTradeCalendarRows"
          v-loading="loadingTradeCalendar"
          class="stocks-table theme-table"
          height="260"
          row-key="cal_date"
        >
          <el-table-column prop="exchange" :label="t('adminStocks.tradeCal.exchange')" min-width="100" />
          <el-table-column prop="cal_date" :label="t('adminStocks.tradeCal.calDate')" min-width="120" />
          <el-table-column :label="t('adminStocks.tradeCal.isOpen')" min-width="120">
            <template #default="scope">
              <el-tag :type="scope.row.is_open === '1' ? 'success' : 'info'">
                {{ scope.row.is_open === '1' ? t('adminStocks.tradeCal.openOnly') : t('adminStocks.tradeCal.closedOnly') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="pretrade_date" :label="t('adminStocks.tradeCal.pretradeDate')" min-width="140" />
        </el-table>

        <div class="pagination-wrap trade-cal-pagination-wrap">
          <el-pagination
            data-testid="trade-cal-pagination"
            background
            layout="total, sizes, prev, pager, next"
            :total="tradeCalendarPagination.total"
            :current-page="tradeCalendarPagination.page"
            :page-size="tradeCalendarPagination.pageSize"
            :page-sizes="[20, 50, 100]"
            @current-change="handleTradeCalendarPageChange"
            @size-change="handleTradeCalendarPageSizeChange"
          />
        </div>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.admin-page {
  display: grid;
  gap: 1rem;
}

.control-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: #f7b500;
  letter-spacing: 0.14em;
  font-size: 0.74rem;
  text-transform: uppercase;
}

h1 {
  margin: 0.38rem 0 0.25rem;
}

.section-note {
  margin: 0;
  color: var(--terminal-muted);
}

.status-chips {
  display: flex;
  gap: 0.6rem;
}

.status-chip {
  min-width: 118px;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  background: linear-gradient(150deg, rgba(25, 40, 63, 0.95), rgba(11, 20, 35, 0.96));
  display: grid;
  gap: 0.2rem;
}

.status-chip span {
  font-size: 0.72rem;
  color: var(--terminal-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-family: 'IBM Plex Mono', monospace;
}

.status-chip strong {
  font-size: 1.25rem;
}

.status-chip.success {
  box-shadow: inset 0 0 0 1px rgba(106, 208, 143, 0.24);
}

.status-chip.danger {
  box-shadow: inset 0 0 0 1px rgba(247, 83, 113, 0.25);
}

.admin-card {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(19, 29, 48, 0.95), rgba(9, 16, 30, 0.97));
  box-shadow: var(--terminal-shadow);
}

.filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto auto auto;
  gap: 0.6rem;
  margin-bottom: 0.8rem;
  align-items: center;
}

.parameter-bar {
  margin-bottom: 0.8rem;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.parameter-label {
  font-size: 0.74rem;
  color: var(--terminal-muted);
  text-transform: uppercase;
  letter-spacing: 0.09em;
  font-family: 'IBM Plex Mono', monospace;
}

.stocks-table {
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  overflow: hidden;
}

.table-shell {
  border: 1px solid color-mix(in srgb, var(--terminal-border) 75%, transparent);
  border-radius: 14px;
  padding: 0.45rem;
  background: linear-gradient(180deg, rgba(12, 20, 35, 0.94), rgba(8, 15, 28, 0.95));
}

.pagination-wrap {
  margin-top: 0.9rem;
  display: flex;
  justify-content: flex-end;
}

.trade-cal-panel {
  margin-top: 1rem;
  border-top: 1px dashed color-mix(in srgb, var(--terminal-border) 72%, transparent);
  padding-top: 0.9rem;
  display: grid;
  gap: 0.65rem;
}

.trade-cal-pagination-wrap {
  margin-top: 0.5rem;
}

.trade-cal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.trade-cal-header h3 {
  margin: 0;
}

.trade-cal-filters {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 0.55rem;
}

.trade-cal-field {
  width: 100%;
}

@media (max-width: 980px) {
  .control-header {
    flex-direction: column;
  }

  .filters {
    grid-template-columns: 1fr;
  }

  .trade-cal-filters {
    grid-template-columns: 1fr;
  }
}
</style>
