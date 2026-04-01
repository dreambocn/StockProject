import { ref } from 'vue'
import { defineStore } from 'pinia'

import {
  policyApi,
  type PolicyDocumentDetail,
  type PolicyDocumentListItem,
  type PolicyFilters,
} from '../api/policy'

type PolicySearchScope = 'basic' | 'fulltext'

interface PolicySessionCache {
  filters: PolicyFilters | null
  filtersFetchedAt: number
  documents: {
    items: PolicyDocumentListItem[]
    total: number
    page: number
    keyword: string
    authority: string
    category: string
    macroTopic: string
    searchScope: PolicySearchScope
  }
  documentsFetchedAt: number
  detailById: Record<string, PolicyDocumentDetail>
  selectedDocumentId: string | null
}

const POLICY_SESSION_STORAGE_KEY = 'policy.session'
const CACHE_TTL_MS = 5 * 60 * 1000
export const POLICY_DOCUMENT_PAGE_SIZE = 12

const buildDefaultCache = (): PolicySessionCache => ({
  filters: null,
  filtersFetchedAt: 0,
  documents: {
    items: [],
    total: 0,
    page: 1,
    keyword: '',
    authority: '',
    category: '',
    macroTopic: '',
    searchScope: 'basic',
  },
  documentsFetchedAt: 0,
  detailById: {},
  selectedDocumentId: null,
})

let cache = buildDefaultCache()
let storageHydrated = false

const canUseSessionStorage = () =>
  typeof window !== 'undefined' && typeof window.sessionStorage !== 'undefined'

const writeCacheToSessionStorage = () => {
  if (!canUseSessionStorage()) {
    return
  }
  window.sessionStorage.setItem(POLICY_SESSION_STORAGE_KEY, JSON.stringify(cache))
}

const hydrateCacheFromSessionStorage = () => {
  if (storageHydrated || !canUseSessionStorage()) {
    return
  }
  storageHydrated = true
  try {
    const raw = window.sessionStorage.getItem(POLICY_SESSION_STORAGE_KEY)
    if (!raw) {
      return
    }
    const parsed = JSON.parse(raw) as Partial<PolicySessionCache>
    cache = {
      ...buildDefaultCache(),
      ...parsed,
      documents: {
        ...buildDefaultCache().documents,
        ...(parsed.documents ?? {}),
      },
      detailById: parsed.detailById ?? {},
    }
  } catch {
    cache = buildDefaultCache()
  }
}

export const resetPolicySessionCache = () => {
  cache = buildDefaultCache()
  storageHydrated = false
  if (canUseSessionStorage()) {
    window.sessionStorage.removeItem(POLICY_SESSION_STORAGE_KEY)
  }
}

export const usePolicyStore = defineStore('policy', () => {
  hydrateCacheFromSessionStorage()

  const filters = ref<PolicyFilters>({ authorities: [], categories: [], macro_topics: [] })
  const items = ref<PolicyDocumentListItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const keyword = ref('')
  const selectedAuthority = ref('')
  const selectedCategory = ref('')
  const selectedMacroTopic = ref('')
  const searchScope = ref<PolicySearchScope>('basic')
  const selectedDocumentId = ref<string | null>(null)
  const selectedDetail = ref<PolicyDocumentDetail | null>(null)
  const filtersFetchedAt = ref(0)
  const documentsFetchedAt = ref(0)

  const loading = ref(false)
  const detailLoading = ref(false)

  let documentGeneration = 0
  let detailGeneration = 0

  const syncStateFromCache = () => {
    filters.value = cache.filters ?? { authorities: [], categories: [], macro_topics: [] }
    filtersFetchedAt.value = cache.filtersFetchedAt
    items.value = cache.documents.items
    total.value = cache.documents.total
    page.value = cache.documents.page
    keyword.value = cache.documents.keyword
    selectedAuthority.value = cache.documents.authority
    selectedCategory.value = cache.documents.category
    selectedMacroTopic.value = cache.documents.macroTopic
    searchScope.value = cache.documents.searchScope
    selectedDocumentId.value = cache.selectedDocumentId
    selectedDetail.value = cache.selectedDocumentId
      ? cache.detailById[cache.selectedDocumentId] ?? null
      : null
    documentsFetchedAt.value = cache.documentsFetchedAt
  }

  const persistDocumentsCache = () => {
    cache.documents = {
      items: items.value,
      total: total.value,
      page: page.value,
      keyword: keyword.value,
      authority: selectedAuthority.value,
      category: selectedCategory.value,
      macroTopic: selectedMacroTopic.value,
      searchScope: searchScope.value,
    }
    cache.documentsFetchedAt = Date.now()
    documentsFetchedAt.value = cache.documentsFetchedAt
    writeCacheToSessionStorage()
  }

  const persistFiltersCache = () => {
    cache.filters = filters.value
    cache.filtersFetchedAt = Date.now()
    filtersFetchedAt.value = cache.filtersFetchedAt
    writeCacheToSessionStorage()
  }

  const isFiltersCacheFresh = () =>
    cache.filtersFetchedAt > 0 && Date.now() - cache.filtersFetchedAt < CACHE_TTL_MS

  const isDocumentsCacheFresh = () =>
    cache.documentsFetchedAt > 0 && Date.now() - cache.documentsFetchedAt < CACHE_TTL_MS

  const isDocumentsCacheHit = () => {
    if (!isDocumentsCacheFresh()) {
      return false
    }
    const documents = cache.documents
    return (
      documents.page === page.value &&
      documents.keyword === keyword.value &&
      documents.authority === selectedAuthority.value &&
      documents.category === selectedCategory.value &&
      documents.macroTopic === selectedMacroTopic.value &&
      documents.searchScope === searchScope.value
    )
  }

  const hydrateFromCache = () => {
    syncStateFromCache()
  }

  const loadFilters = async ({ background = false }: { background?: boolean } = {}) => {
    if (isFiltersCacheFresh() && cache.filters && !background) {
      filters.value = cache.filters
      filtersFetchedAt.value = cache.filtersFetchedAt
      return
    }

    const result = await policyApi.getFilters()
    filters.value = result
    persistFiltersCache()
  }

  const loadDetail = async (documentId: string) => {
    selectedDocumentId.value = documentId
    cache.selectedDocumentId = documentId
    writeCacheToSessionStorage()

    if (cache.detailById[documentId]) {
      selectedDetail.value = cache.detailById[documentId]
      return
    }

    const generation = ++detailGeneration
    detailLoading.value = true
    try {
      const detail = await policyApi.getDocument(documentId)
      if (detailGeneration !== generation) {
        return
      }
      selectedDetail.value = detail
      cache.detailById[documentId] = detail
      writeCacheToSessionStorage()
    } finally {
      if (detailGeneration === generation) {
        detailLoading.value = false
      }
    }
  }

  const autoSelectFirst = async () => {
    if (items.value.length === 0) {
      selectedDocumentId.value = null
      selectedDetail.value = null
      cache.selectedDocumentId = null
      writeCacheToSessionStorage()
      return
    }

    const nextDocumentId = items.value.some((item) => item.id === selectedDocumentId.value)
      ? selectedDocumentId.value
      : items.value[0]!.id

    if (!nextDocumentId) {
      return
    }

    if (cache.detailById[nextDocumentId]) {
      selectedDocumentId.value = nextDocumentId
      selectedDetail.value = cache.detailById[nextDocumentId]
      cache.selectedDocumentId = nextDocumentId
      writeCacheToSessionStorage()
      return
    }

    await loadDetail(nextDocumentId)
  }

  const loadDocuments = async ({ background = false }: { background?: boolean } = {}) => {
    const generation = ++documentGeneration

    if (isDocumentsCacheHit() && !background) {
      items.value = cache.documents.items
      total.value = cache.documents.total
      documentsFetchedAt.value = cache.documentsFetchedAt
      await autoSelectFirst()
      return
    }

    if (!background) {
      loading.value = true
    }
    try {
      const payload = await policyApi.getDocuments({
        authority: selectedAuthority.value || undefined,
        category: selectedCategory.value || undefined,
        macroTopic: selectedMacroTopic.value || undefined,
        keyword: keyword.value || undefined,
        searchScope: searchScope.value,
        page: page.value,
        pageSize: POLICY_DOCUMENT_PAGE_SIZE,
      })
      if (documentGeneration !== generation) {
        return
      }
      items.value = payload.items
      total.value = payload.total
      page.value = payload.page
      persistDocumentsCache()
      await autoSelectFirst()
    } finally {
      if (!background && documentGeneration === generation) {
        loading.value = false
      }
    }
  }

  const clearCache = () => {
    const currentQuery = {
      page: page.value,
      keyword: keyword.value,
      authority: selectedAuthority.value,
      category: selectedCategory.value,
      macroTopic: selectedMacroTopic.value,
      searchScope: searchScope.value,
    }
    cache = buildDefaultCache()
    cache.documents.page = currentQuery.page
    cache.documents.keyword = currentQuery.keyword
    cache.documents.authority = currentQuery.authority
    cache.documents.category = currentQuery.category
    cache.documents.macroTopic = currentQuery.macroTopic
    cache.documents.searchScope = currentQuery.searchScope
    syncStateFromCache()
    writeCacheToSessionStorage()
  }

  syncStateFromCache()

  return {
    filters,
    items,
    total,
    page,
    keyword,
    selectedAuthority,
    selectedCategory,
    selectedMacroTopic,
    searchScope,
    selectedDocumentId,
    selectedDetail,
    filtersFetchedAt,
    documentsFetchedAt,
    loading,
    detailLoading,
    hydrateFromCache,
    isFiltersCacheFresh,
    isDocumentsCacheFresh,
    loadFilters,
    loadDocuments,
    loadDetail,
    autoSelectFirst,
    clearCache,
  }
})
