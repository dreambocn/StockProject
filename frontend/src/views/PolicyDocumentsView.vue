<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '../api/http'
import {
  policyApi,
  type PolicyDocumentDetail,
  type PolicyDocumentListItem,
  type PolicyFilters,
} from '../api/policy'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()

const loading = ref(false)
const detailLoading = ref(false)
const syncLoading = ref(false)
const errorMessage = ref('')
const syncMessage = ref('')
const filters = ref<PolicyFilters>({
  authorities: [],
  categories: [],
  macro_topics: [],
})
const items = ref<PolicyDocumentListItem[]>([])
const total = ref(0)
const keyword = ref('')
const selectedAuthority = ref('')
const selectedCategory = ref('')
const selectedMacroTopic = ref('')
const selectedDetail = ref<PolicyDocumentDetail | null>(null)

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

const loadFilters = async () => {
  filters.value = await policyApi.getFilters()
}

const loadDocuments = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const payload = await policyApi.getDocuments({
      authority: selectedAuthority.value || undefined,
      category: selectedCategory.value || undefined,
      macroTopic: selectedMacroTopic.value || undefined,
      keyword: keyword.value || undefined,
      page: 1,
      pageSize: 20,
    })
    items.value = payload.items
    total.value = payload.total
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

const openDetail = async (documentId: string) => {
  detailLoading.value = true
  try {
    // 关键流程：详情正文和附件单独请求，避免列表接口过重。
    selectedDetail.value = await policyApi.getDocument(documentId)
  } finally {
    detailLoading.value = false
  }
}

const searchDocuments = async () => {
  await loadDocuments()
}

const syncDocuments = async () => {
  if (!authStore.isAdmin) {
    return
  }
  syncLoading.value = true
  syncMessage.value = ''
  try {
    const result = await policyApi.syncDocuments(true)
    syncMessage.value = t('policyDocuments.syncResult', {
      inserted: result.inserted_count,
      updated: result.updated_count,
      failed: result.failed_provider_count,
    })
    await loadDocuments()
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
  await loadFilters()
  await loadDocuments()
})
</script>

<template>
  <section
    class="policy-documents-page"
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
        v-model="keyword"
        data-testid="policy-keyword-input"
        type="text"
        class="filter-input"
        :placeholder="t('policyDocuments.keywordPlaceholder')"
      />
      <select v-model="selectedAuthority" class="filter-select">
        <option value="">{{ t('policyDocuments.filterAllAuthority') }}</option>
        <option
          v-for="item in filters.authorities"
          :key="item.value"
          :value="item.value"
        >
          {{ item.label }}
        </option>
      </select>
      <select v-model="selectedCategory" class="filter-select">
        <option value="">{{ t('policyDocuments.filterAllCategory') }}</option>
        <option
          v-for="item in filters.categories"
          :key="item.value"
          :value="item.value"
        >
          {{ item.label }}
        </option>
      </select>
      <select v-model="selectedMacroTopic" class="filter-select">
        <option value="">{{ t('policyDocuments.filterAllTopic') }}</option>
        <option
          v-for="item in filters.macro_topics"
          :key="item.value"
          :value="item.value"
        >
          {{ item.label }}
        </option>
      </select>
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
      <section class="list-panel">
        <div class="list-header">
          <h2>{{ t('policyDocuments.listTitle') }}</h2>
          <span>{{ t('policyDocuments.total', { total }) }}</span>
        </div>

        <p v-if="loading" class="section-note">{{ t('policyDocuments.loading') }}</p>
        <p v-else-if="items.length === 0" class="section-note">{{ t('policyDocuments.empty') }}</p>

        <article
          v-for="item in items"
          :key="item.id"
          class="policy-card"
        >
          <div class="policy-card__meta">
            <span>{{ item.issuing_authority || item.source }}</span>
            <span>{{ formatTime(item.published_at) }}</span>
          </div>
          <h3>{{ item.title }}</h3>
          <p class="policy-card__summary">{{ item.summary || t('analysisWorkbench.dataMissing') }}</p>
          <div class="policy-card__footer">
            <a
              v-if="item.url"
              :href="item.url"
              target="_blank"
              rel="noreferrer"
            >
              {{ t('policyDocuments.openSource') }}
            </a>
            <button type="button" @click="openDetail(item.id)">
              {{ t('policyDocuments.viewDetail') }}
            </button>
          </div>
        </article>
      </section>

      <section class="detail-panel">
        <div class="list-header">
          <h2>{{ t('policyDocuments.detailTitle') }}</h2>
        </div>

        <p v-if="detailLoading" class="section-note">{{ t('policyDocuments.detailLoading') }}</p>
        <p v-else-if="!selectedDetail" class="section-note">{{ t('policyDocuments.detailEmpty') }}</p>

        <template v-else>
          <h3>{{ selectedDetail.title }}</h3>
          <p class="detail-meta">
            {{ selectedDetail.issuing_authority || selectedDetail.source }}
            ·
            {{ formatTime(selectedDetail.published_at) }}
          </p>
          <p class="detail-content">
            {{ selectedDetail.content_text || selectedDetail.summary || t('analysisWorkbench.dataMissing') }}
          </p>

          <div v-if="selectedDetail.attachments.length" class="attachment-list">
            <h4>{{ t('policyDocuments.attachments') }}</h4>
            <a
              v-for="item in selectedDetail.attachments"
              :key="item.attachment_url"
              :href="item.attachment_url"
              target="_blank"
              rel="noreferrer"
            >
              {{ item.attachment_name || item.attachment_url }}
            </a>
          </div>
        </template>
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
  background:
    radial-gradient(circle at top right, rgba(122, 206, 255, 0.14), transparent 55%),
    linear-gradient(145deg, rgba(20, 32, 54, 0.96), rgba(9, 17, 31, 0.98));
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
  color: #f7b500;
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
  grid-template-columns: minmax(180px, 1.4fr) repeat(3, minmax(120px, 1fr)) auto;
  gap: 0.75rem;
}

.filter-input,
.filter-select,
.search-button,
.sync-button {
  border-radius: 12px;
  border: 1px solid var(--terminal-border);
  background: rgba(9, 17, 31, 0.72);
  color: var(--terminal-text);
  padding: 0.72rem 0.85rem;
}

.search-button,
.sync-button,
.policy-card__footer button {
  cursor: pointer;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 1rem;
}

.list-panel,
.detail-panel {
  padding: 1rem;
  display: grid;
  gap: 0.85rem;
}

.list-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
}

.policy-card {
  border: 1px solid rgba(123, 197, 255, 0.22);
  border-radius: 14px;
  padding: 0.95rem;
  display: grid;
  gap: 0.55rem;
  background: rgba(8, 16, 30, 0.82);
}

.policy-card__meta,
.policy-card__footer {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: center;
  font-size: 0.86rem;
}

.detail-content {
  white-space: pre-wrap;
  line-height: 1.7;
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
}
</style>
