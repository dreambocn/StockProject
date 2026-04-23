<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '../api/http'
import { policyApi } from '../api/policy'
import { useAuthStore } from '../stores/auth'
import { POLICY_DOCUMENT_PAGE_SIZE, usePolicyStore } from '../stores/policy'

const { t } = useI18n()
const authStore = useAuthStore()
const store = usePolicyStore()

const errorMessage = ref('')
const detailErrorMessage = ref('')
const syncMessage = ref('')
const syncLoading = ref(false)

const formKeyword = ref('')
const formSelectedAuthority = ref('')
const formSelectedCategory = ref('')
const formSelectedMacroTopic = ref('')
const fulltextEnabled = ref(false)

const hasPagination = computed(() => store.total > POLICY_DOCUMENT_PAGE_SIZE)
const panelLayoutStyle = {
  '--policy-panel-height': '680px',
  '--policy-mobile-list-height': '360px',
}

const formatTime = (value: string | null) => {
  if (!value) {
    return '--'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

const syncFormFromStore = () => {
  formKeyword.value = store.keyword
  formSelectedAuthority.value = store.selectedAuthority
  formSelectedCategory.value = store.selectedCategory
  formSelectedMacroTopic.value = store.selectedMacroTopic
  fulltextEnabled.value = store.searchScope === 'fulltext'
}

const loadDocuments = async ({ background = false }: { background?: boolean } = {}) => {
  if (!background) {
    errorMessage.value = ''
  }
  try {
    await store.loadDocuments({ background })
  } catch (error) {
    if (!background) {
      if (error instanceof ApiError) {
        errorMessage.value = error.message
      } else {
        errorMessage.value = t('errors.fallback')
      }
    }
  }
}

const loadFilters = async ({ background = false }: { background?: boolean } = {}) => {
  try {
    await store.loadFilters({ background })
  } catch (error) {
    if (!background) {
      if (error instanceof ApiError) {
        errorMessage.value = error.message
      } else {
        errorMessage.value = t('errors.fallback')
      }
    }
  }
}

const openDetail = async (documentId: string) => {
  detailErrorMessage.value = ''
  try {
    await store.loadDetail(documentId)
  } catch (error) {
    if (error instanceof ApiError) {
      detailErrorMessage.value = error.message
    } else {
      detailErrorMessage.value = t('errors.fallback')
    }
  }
}

const searchDocuments = async () => {
  store.page = 1
  store.keyword = formKeyword.value.trim()
  store.selectedAuthority = formSelectedAuthority.value
  store.selectedCategory = formSelectedCategory.value
  store.selectedMacroTopic = formSelectedMacroTopic.value
  store.searchScope = fulltextEnabled.value ? 'fulltext' : 'basic'
  await loadDocuments()
}

const handlePageChange = async (newPage: number) => {
  store.page = newPage
  await loadDocuments()
}

const syncDocuments = async () => {
  if (!authStore.isAdmin) {
    return
  }
  syncLoading.value = true
  syncMessage.value = ''
  try {
    const result = await policyApi.syncDocuments(true, authStore.accessToken)
    syncMessage.value = t('policyDocuments.syncResult', {
      inserted: result.inserted_count,
      updated: result.updated_count,
      failed: result.failed_provider_count,
    })
    detailErrorMessage.value = ''
    store.clearCache()
    await Promise.all([loadFilters(), loadDocuments()])
  } catch (error) {
    if (error instanceof ApiError) {
      syncMessage.value = error.message
    } else {
      syncMessage.value = t('errors.fallback')
    }
  } finally {
    syncLoading.value = false
  }
}

onMounted(async () => {
  // 关键流程：先恢复会话缓存，让页面立即可见；随后根据缓存新鲜度决定是静默刷新还是阻塞拉取。
  store.hydrateFromCache()
  syncFormFromStore()

  const shouldRefreshFiltersInBackground =
    store.filters.authorities.length > 0 && store.isFiltersCacheFresh()
  const shouldRefreshDocumentsInBackground =
    store.items.length > 0 && store.isDocumentsCacheFresh()

  await Promise.all([
    loadFilters({ background: shouldRefreshFiltersInBackground }),
    loadDocuments({ background: shouldRefreshDocumentsInBackground }),
  ])
})
</script>

<template>
  <section
    data-testid="policy-documents-page"
    class="policy-documents-page"
    :style="panelLayoutStyle"
    v-motion
    :initial="{ opacity: 0, y: 16 }"
    :enter="{ opacity: 1, y: 0 }"
  >
    <header class="panel-header">
      <div>
        <p class="panel-kicker">{{ t('policyDocuments.kicker') }}</p>
        <h1>{{ t('policyDocuments.title') }}</h1>
        <p class="section-note">{{ t('policyDocuments.note') }}</p>
      </div>
      <button
        v-if="authStore.isAdmin"
        type="button"
        class="sync-button"
        :disabled="syncLoading"
        @click="syncDocuments"
      >
        {{ syncLoading ? t('policyDocuments.syncing') : t('policyDocuments.syncNow') }}
      </button>
    </header>

    <section class="filter-panel">
      <input
        v-model="formKeyword"
        data-testid="policy-keyword-input"
        type="text"
        class="filter-input"
        :placeholder="t('policyDocuments.keywordPlaceholder')"
      />
      <select v-model="formSelectedAuthority" class="filter-select">
        <option value="">{{ t('policyDocuments.filterAllAuthority') }}</option>
        <option
          v-for="item in store.filters.authorities"
          :key="item.value"
          :value="item.value"
        >
          {{ item.label }}
        </option>
      </select>
      <select v-model="formSelectedCategory" class="filter-select">
        <option value="">{{ t('policyDocuments.filterAllCategory') }}</option>
        <option
          v-for="item in store.filters.categories"
          :key="item.value"
          :value="item.value"
        >
          {{ item.label }}
        </option>
      </select>
      <select v-model="formSelectedMacroTopic" class="filter-select">
        <option value="">{{ t('policyDocuments.filterAllTopic') }}</option>
        <option
          v-for="item in store.filters.macro_topics"
          :key="item.value"
          :value="item.value"
        >
          {{ item.label }}
        </option>
      </select>
      <label class="fulltext-toggle">
        <input
          v-model="fulltextEnabled"
          data-testid="policy-fulltext-toggle"
          type="checkbox"
        />
        <span>{{ t('policyDocuments.fulltextToggle') }}</span>
      </label>
      <button
        data-testid="policy-search-button"
        type="button"
        class="search-button"
        @click="searchDocuments"
      >
        {{ t('policyDocuments.search') }}
      </button>
    </section>

    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <p v-if="syncMessage" class="sync-message">{{ syncMessage }}</p>

    <div class="content-grid">
      <section class="list-panel" data-testid="policy-list-panel">
        <div class="list-header">
          <div>
            <h2>{{ t('policyDocuments.listTitle') }}</h2>
            <p class="section-note">{{ t('policyDocuments.total', { total: store.total }) }}</p>
          </div>
        </div>

        <el-scrollbar
          data-testid="policy-list-scrollbar"
          class="policy-panel-scrollbar"
          wrap-class="policy-panel-scrollbar__wrap"
          :always="true"
          height="100%"
          :aria-label="t('policyDocuments.listTitle')"
        >
          <div class="list-scroll">
            <p v-if="store.loading && store.items.length === 0" class="section-note">
              {{ t('policyDocuments.loading') }}
            </p>
            <p v-else-if="store.items.length === 0" class="section-note">
              {{ t('policyDocuments.empty') }}
            </p>

            <article
              v-for="item in store.items"
              :key="item.id"
              class="policy-card"
              :class="{ selected: store.selectedDocumentId === item.id }"
            >
              <div class="policy-card__meta">
                <span>{{ item.issuing_authority || item.source }}</span>
                <span>{{ formatTime(item.published_at) }}</span>
              </div>
              <h3>{{ item.title }}</h3>
              <p class="policy-card__summary">
                {{ item.summary || t('analysisWorkbench.dataMissing') }}
              </p>
              <div class="policy-card__footer">
                <a
                  v-if="item.url"
                  :href="item.url"
                  target="_blank"
                  rel="noreferrer"
                >
                  {{ t('policyDocuments.openSource') }}
                </a>
                <button type="button" class="detail-button" @click="openDetail(item.id)">
                  {{ t('policyDocuments.viewDetail') }}
                </button>
              </div>
            </article>
          </div>
        </el-scrollbar>

        <div v-if="hasPagination" class="pagination-wrap">
          <el-pagination
            class="list-pagination"
            background
            layout="prev, pager, next"
            :current-page="store.page"
            :page-size="POLICY_DOCUMENT_PAGE_SIZE"
            :total="store.total"
            @current-change="handlePageChange"
          />
        </div>
      </section>

      <section class="detail-panel" data-testid="policy-detail-panel">
        <div class="detail-header">
          <div>
            <h2>{{ t('policyDocuments.detailTitle') }}</h2>
            <p v-if="store.selectedDetail" class="section-note">
              {{ store.selectedDetail.document_no || store.selectedDetail.policy_level || store.selectedDetail.category || t('analysisWorkbench.dataMissing') }}
            </p>
          </div>
        </div>

        <el-scrollbar
          data-testid="policy-detail-scrollbar"
          class="policy-panel-scrollbar"
          wrap-class="policy-panel-scrollbar__wrap"
          :always="true"
          height="100%"
          :aria-label="t('policyDocuments.detailTitle')"
        >
          <div class="detail-scroll">
            <p v-if="store.detailLoading && !store.selectedDetail" class="section-note">
              {{ t('policyDocuments.detailLoading') }}
            </p>
            <p v-else-if="!store.selectedDetail" class="section-note">
              {{ t('policyDocuments.detailEmpty') }}
            </p>
            <p v-if="detailErrorMessage" class="error-message">{{ detailErrorMessage }}</p>

            <template v-if="store.selectedDetail">
              <h3>{{ store.selectedDetail.title }}</h3>
              <p class="detail-meta">
                {{ store.selectedDetail.issuing_authority || store.selectedDetail.source }}
                ·
                {{ formatTime(store.selectedDetail.published_at) }}
              </p>
              <div class="detail-content-wrapper">
                <p class="detail-content">
                  {{ store.selectedDetail.content_text || store.selectedDetail.summary || t('analysisWorkbench.dataMissing') }}
                </p>
              </div>

              <div v-if="store.selectedDetail.attachments.length" class="attachment-list">
                <h4>{{ t('policyDocuments.attachments') }}</h4>
                <a
                  v-for="item in store.selectedDetail.attachments"
                  :key="item.attachment_url"
                  :href="item.attachment_url"
                  target="_blank"
                  rel="noreferrer"
                >
                  {{ item.attachment_name || item.attachment_url }}
                </a>
              </div>
            </template>
          </div>
        </el-scrollbar>
      </section>
    </div>
  </section>
</template>

<style scoped>
.policy-documents-page {
  display: grid;
  gap: 1rem;
}

.panel-header,
.filter-panel,
.list-panel,
.detail-panel {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: var(--terminal-hero-bg);
  box-shadow: var(--terminal-shadow);
}

.panel-header {
  padding: 1rem 1.1rem;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: var(--terminal-warning);
  letter-spacing: 0.14em;
  font-size: 0.74rem;
  text-transform: uppercase;
}

.section-note,
.detail-meta,
.policy-card__summary,
.sync-message,
.error-message {
  color: var(--terminal-muted);
}

.filter-panel {
  padding: 1rem;
  display: grid;
  grid-template-columns: minmax(200px, 1.4fr) repeat(3, minmax(130px, 1fr)) auto auto;
  gap: 0.75rem;
  align-items: center;
}

.filter-input,
.filter-select,
.search-button,
.sync-button,
.detail-button {
  border-radius: 12px;
  border: 1px solid var(--terminal-border);
  background: var(--terminal-input-bg);
  color: var(--terminal-text);
  padding: 0.72rem 0.85rem;
}

.search-button,
.sync-button,
.detail-button {
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    transform 0.2s ease,
    background-color 0.2s ease;
}

.search-button:hover,
.sync-button:hover,
.detail-button:hover {
  border-color: color-mix(in srgb, var(--terminal-primary) 60%, var(--terminal-border));
  transform: translateY(-1px);
}

.fulltext-toggle {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 46px;
  padding: 0 0.75rem;
  border-radius: 12px;
  border: 1px solid var(--terminal-border);
  background: color-mix(in srgb, var(--terminal-input-bg) 90%, var(--terminal-panel) 10%);
  color: var(--terminal-muted);
  font-size: 0.86rem;
  white-space: nowrap;
}

.fulltext-toggle input[type='checkbox'] {
  accent-color: var(--terminal-primary);
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(360px, 420px) minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

.list-panel,
.detail-panel {
  display: grid;
  gap: 0;
  overflow: hidden;
  height: var(--policy-panel-height);
  min-height: 0;
}

.list-panel {
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.detail-panel {
  grid-template-rows: auto minmax(0, 1fr);
}

.list-header,
.detail-header {
  padding: 1rem 1rem 0.7rem;
}

.list-header h2,
.detail-header h2 {
  margin: 0;
}

.policy-panel-scrollbar {
  flex: 1;
  min-height: 0;
}

.list-panel :deep(.policy-panel-scrollbar__wrap),
.detail-panel :deep(.policy-panel-scrollbar__wrap) {
  min-height: 0;
  overflow-x: hidden;
  overscroll-behavior: contain;
}

.list-panel :deep(.el-scrollbar__bar.is-vertical),
.detail-panel :deep(.el-scrollbar__bar.is-vertical) {
  width: 8px;
  right: 0;
}

.list-panel :deep(.el-scrollbar__bar.is-vertical > div),
.detail-panel :deep(.el-scrollbar__bar.is-vertical > div) {
  border: 1px solid rgba(6, 12, 21, 0.45);
  border-radius: 999px;
  background:
    linear-gradient(180deg, rgba(123, 197, 255, 0.62), rgba(61, 169, 252, 0.32)),
    color-mix(in srgb, var(--terminal-primary) 42%, rgba(255, 255, 255, 0.08));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.08),
    0 0 10px rgba(61, 169, 252, 0.18);
}

.list-panel :deep(.el-scrollbar__bar.is-vertical:hover > div),
.detail-panel :deep(.el-scrollbar__bar.is-vertical:hover > div) {
  background:
    linear-gradient(180deg, rgba(123, 197, 255, 0.8), rgba(61, 169, 252, 0.5)),
    color-mix(in srgb, var(--terminal-primary) 58%, rgba(255, 255, 255, 0.12));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.12),
    0 0 14px rgba(61, 169, 252, 0.28);
}

.list-panel :deep(.el-scrollbar__thumb),
.detail-panel :deep(.el-scrollbar__thumb) {
  opacity: 1;
}

.list-scroll,
.detail-scroll {
  min-height: 0;
  padding: 0 1rem 1rem;
  display: grid;
  gap: 0.85rem;
  align-content: start;
}

.policy-card {
  border: 1px solid rgba(123, 197, 255, 0.18);
  border-radius: 14px;
  padding: 0.95rem;
  display: grid;
  gap: 0.55rem;
  background: var(--terminal-card-soft-bg-strong);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.policy-card:hover,
.policy-card.selected {
  border-color: rgba(123, 197, 255, 0.42);
  box-shadow: inset 0 0 0 1px rgba(123, 197, 255, 0.12);
  transform: translateY(-1px);
}

.policy-card__meta,
.policy-card__footer {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: center;
  font-size: 0.86rem;
}

.pagination-wrap {
  padding: 0 1rem 1rem;
  display: flex;
  justify-content: center;
}

.detail-content-wrapper {
  max-width: 72ch;
}

.detail-content {
  white-space: pre-wrap;
  line-height: 1.72;
  margin: 0;
}

.attachment-list {
  display: grid;
  gap: 0.45rem;
}

@media (max-width: 980px) {
  .filter-panel,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .list-panel {
    height: var(--policy-mobile-list-height);
  }

  .detail-panel {
    height: auto;
  }
}
</style>
