<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import {
  newsApi,
  type CandidateSourceBreakdownItem,
  type HotNewsItem,
  type MacroImpactProfile,
} from '../api/news'
import { ApiError } from '../api/http'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const HOT_NEWS_ANCHOR_STORAGE_KEY = 'hot-news-anchor-event-selections'

const loading = ref(false)
const impactLoading = ref(false)
const errorMessage = ref('')
const items = ref<HotNewsItem[]>([])
const impactProfiles = ref<MacroImpactProfile[]>([])
const selectedAnchorEventIds = ref<Record<string, string>>({})
const topicOptions = [
  'all',
  'geopolitical_conflict',
  'monetary_policy',
  'commodity_supply',
  'regulation_policy',
  'other',
] as const

const normalizeTopic = (value: string) =>
  topicOptions.includes(value as (typeof topicOptions)[number]) ? value : 'all'

const selectedTopic = ref(normalizeTopic(String(route.query.topic ?? 'all')))

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

const formatCandidateSourceBreakdown = (items?: CandidateSourceBreakdownItem[]) => {
  if (!items || items.length === 0) {
    return t('analysisWorkbench.dataMissing')
  }
  return items
    .map((item) => `${t(`hotNews.candidateSources.${item.source}`)} ${item.count}`)
    .join(' / ')
}

const formatCandidateEvidenceTime = (value: string | null) => {
  if (!value) {
    return '--'
  }
  return formatTime(value)
}

const formatCandidateEvidenceKind = (value: string) =>
  t(`hotNews.candidateEvidenceKinds.${value}`)

const loadHotNews = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    // 关键流程：热点页只请求全局快讯接口，不混入个股接口结果，保证信息语义清晰。
    // 关键业务分支：仅当用户选择具体主题时携带 topic 参数，all 分支保持默认全量热点流。
    const topic = selectedTopic.value === 'all' ? undefined : selectedTopic.value
    items.value = await newsApi.getHotNews(100, topic)
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

const loadImpactProfiles = async () => {
  impactLoading.value = true
  try {
    const topic = selectedTopic.value === 'all' ? undefined : selectedTopic.value
    // 关键流程：影响面板与新闻列表使用同一 topic，保证用户看到的新闻与影响解释语义一致。
    impactProfiles.value = await newsApi.getImpactMap(topic)
  } catch {
    // 降级分支：影响面板失败不影响热点新闻主体浏览，保持页面可读性。
    impactProfiles.value = []
  } finally {
    impactLoading.value = false
  }
}

const getTopicEvents = (topic: string) =>
  items.value.filter((item) => item.macro_topic === topic)

const readPersistedAnchorSelection = () => {
  if (typeof window === 'undefined' || !window.localStorage) {
    return {}
  }
  try {
    const raw = window.localStorage.getItem(HOT_NEWS_ANCHOR_STORAGE_KEY)
    if (!raw) {
      return {}
    }
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') {
      return {}
    }
    return parsed as Record<string, string>
  } catch {
    return {}
  }
}

const persistAnchorSelection = (value: Record<string, string>) => {
  if (typeof window === 'undefined' || !window.localStorage) {
    return
  }
  try {
    window.localStorage.setItem(HOT_NEWS_ANCHOR_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // 降级分支：本地存储不可用时仅保留当前内存状态，不影响页面主链路。
  }
}

const syncAnchorEventSelection = () => {
  const persistedSelection = readPersistedAnchorSelection()
  const nextSelection = { ...persistedSelection, ...selectedAnchorEventIds.value }
  impactProfiles.value.forEach((profile) => {
    const current = nextSelection[profile.topic]
    if (current) {
      return
    }
    const defaultEventId = profile.anchor_event?.event_id
    if (defaultEventId) {
      nextSelection[profile.topic] = defaultEventId
      return
    }
    const firstTopicEvent = getTopicEvents(profile.topic)[0]
    if (firstTopicEvent?.event_id) {
      nextSelection[profile.topic] = firstTopicEvent.event_id
    }
  })
  selectedAnchorEventIds.value = nextSelection
  persistAnchorSelection(nextSelection)
}

const selectTopic = async (topic: string) => {
  if (selectedTopic.value === topic) {
    return
  }
  selectedTopic.value = topic
  await router.replace({
    path: '/news/hot',
    query: topic === 'all' ? {} : { topic },
  })
  await Promise.all([loadHotNews(), loadImpactProfiles()])
}

onMounted(async () => {
  await Promise.all([loadHotNews(), loadImpactProfiles()])
  syncAnchorEventSelection()
})

watch(
  () => String(route.query.topic ?? 'all'),
  async (value) => {
    const normalized = normalizeTopic(value)
    if (normalized === selectedTopic.value) {
      return
    }
    selectedTopic.value = normalized
    await Promise.all([loadHotNews(), loadImpactProfiles()])
    syncAnchorEventSelection()
  },
)

const getAnchorEventForTopic = (profile: MacroImpactProfile) => {
  const selectedEventId = selectedAnchorEventIds.value[profile.topic]
  const matchedEvent = getTopicEvents(profile.topic).find((item) => item.event_id === selectedEventId)
  if (matchedEvent) {
    return matchedEvent
  }
  return (
    getTopicEvents(profile.topic).find((item) => item.event_id === profile.anchor_event?.event_id)
    ?? getTopicEvents(profile.topic)[0]
    ?? null
  )
}

const selectAnchorEvent = (topic: string, eventId: string | null) => {
  if (!eventId) {
    return
  }
  const nextSelection = {
    ...selectedAnchorEventIds.value,
    [topic]: eventId,
  }
  selectedAnchorEventIds.value = nextSelection
  persistAnchorSelection(nextSelection)
}

const goToStockDetail = async (tsCode: string, profile: MacroImpactProfile) => {
  const anchorEvent = getAnchorEventForTopic(profile)
  await router.push({
    path: `/stocks/${encodeURIComponent(tsCode)}`,
    query: {
      topic: profile.topic,
      event_id: anchorEvent?.event_id ?? undefined,
      event_title: anchorEvent?.title ?? profile.anchor_event?.title ?? undefined,
      source: 'hot_news',
    },
  })
}
</script>

<template>
  <section class="hot-news-page" v-motion :initial="{ opacity: 0, y: 12 }" :enter="{ opacity: 1, y: 0 }">
    <header class="section-header">
      <div>
        <p class="section-kicker">{{ t('hotNews.kicker') }}</p>
        <h1>{{ t('hotNews.title') }}</h1>
      </div>
      <el-button :loading="loading" @click="loadHotNews">{{ t('hotNews.refresh') }}</el-button>
    </header>

    <section class="topic-filter-panel">
      <p class="topic-filter-label">{{ t('hotNews.filterLabel') }}</p>
      <div class="topic-filter-list">
        <button
          v-for="topic in topicOptions"
          :key="topic"
          type="button"
          class="topic-filter-chip"
          :class="{ active: selectedTopic === topic }"
          @click="selectTopic(topic)"
        >
          {{ t(`hotNews.topics.${topic}`) }}
        </button>
      </div>
    </section>

    <section class="impact-panel">
      <header class="impact-header">
        <h2>{{ t('hotNews.impactPanel.title') }}</h2>
      </header>
      <el-skeleton v-if="impactLoading" :rows="2" animated />
      <el-empty v-else-if="impactProfiles.length === 0" :description="t('hotNews.impactPanel.empty')" />
      <div v-else class="impact-list">
        <article v-for="profile in impactProfiles" :key="profile.topic" class="impact-item">
          <p class="impact-topic">{{ t(`hotNews.topics.${profile.topic}`) }}</p>
          <div v-if="getAnchorEventForTopic(profile)" class="impact-anchor">
            <strong>{{ t('hotNews.anchorEvent') }}:</strong>
            <span class="impact-anchor__title">{{ getAnchorEventForTopic(profile)?.title }}</span>
            <span class="analysis-token">{{ getAnchorEventForTopic(profile)?.source_coverage ?? profile.anchor_event?.source_coverage }}</span>
          </div>
          <div v-if="getTopicEvents(profile.topic).length > 1" class="impact-anchor-switcher">
            <button
              v-for="eventItem in getTopicEvents(profile.topic)"
              :key="eventItem.event_id ?? eventItem.title"
              type="button"
              class="topic-filter-chip"
              :class="{ active: selectedAnchorEventIds[profile.topic] === eventItem.event_id }"
              @click="selectAnchorEvent(profile.topic, eventItem.event_id)"
            >
              {{ eventItem.title }}
            </button>
          </div>
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.assets') }}:</strong> {{ profile.affected_assets.join(' / ') }}</p>
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.beneficiarySectors') }}:</strong> {{ profile.beneficiary_sectors.join(' / ') }}</p>
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.pressureSectors') }}:</strong> {{ profile.pressure_sectors.join(' / ') }}</p>
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.targets') }}:</strong> {{ profile.a_share_targets.join(' / ') }}</p>
          <div class="impact-row impact-candidate-row">
            <strong class="impact-candidate-label">{{ t('hotNews.impactPanel.candidates') }}:</strong>
            <div v-if="profile.a_share_candidates.length > 0" class="impact-candidate-list">
              <article
                v-for="candidate in profile.a_share_candidates"
                :key="candidate.ts_code"
                class="impact-candidate-item"
              >
                <div class="impact-candidate-head">
                  <div class="impact-candidate-main">
                    <strong>{{ `${candidate.name}(${candidate.ts_code})` }}</strong>
                    <span v-if="candidate.industry" class="impact-candidate-industry">
                      {{ candidate.industry }}
                    </span>
                    <span class="analysis-token">{{ candidate.relevance_score }}</span>
                    <span v-if="candidate.candidate_confidence" class="analysis-token">
                      {{ `${t('hotNews.candidateConfidence')} ${candidate.candidate_confidence}` }}
                    </span>
                    <span
                      v-if="typeof candidate.freshness_score === 'number' && candidate.freshness_score > 0"
                      class="analysis-token"
                    >
                      {{ `${t('hotNews.candidateFreshness')} ${candidate.freshness_score}` }}
                    </span>
                  </div>
                  <el-button
                    plain
                    size="small"
                    class="impact-candidate-action"
                    @click="goToStockDetail(candidate.ts_code, profile)"
                  >
                    {{ t('hotNews.viewDetail') }}
                  </el-button>
                </div>
                <p class="impact-candidate-reason">{{ candidate.evidence_summary }}</p>
                <p
                  v-if="(candidate.source_breakdown?.length ?? 0) > 0"
                  class="impact-candidate-breakdown"
                >
                  <strong>{{ t('hotNews.candidateSourceBreakdown') }}:</strong>
                  {{ formatCandidateSourceBreakdown(candidate.source_breakdown) }}
                </p>
                <div
                  v-if="(candidate.evidence_items?.length ?? 0) > 0"
                  class="impact-candidate-evidence-list"
                >
                  <article
                    v-for="item in candidate.evidence_items ?? []"
                    :key="`${candidate.ts_code}-${item.evidence_kind}-${item.title}`"
                    class="impact-candidate-evidence-card"
                  >
                    <div class="impact-candidate-evidence-head">
                      <span class="analysis-token">
                        {{ formatCandidateEvidenceKind(item.evidence_kind) }}
                      </span>
                      <span class="impact-candidate-evidence-time">
                        {{ formatCandidateEvidenceTime(item.published_at) }}
                      </span>
                    </div>
                    <p class="impact-candidate-evidence-title">{{ item.title }}</p>
                    <p v-if="item.summary" class="impact-candidate-evidence-summary">{{ item.summary }}</p>
                  </article>
                </div>
              </article>
            </div>
            <span v-else>--</span>
          </div>
        </article>
      </div>
    </section>

    <el-alert v-if="errorMessage" :title="errorMessage" type="error" :closable="false" show-icon />
    <el-empty v-if="!loading && items.length === 0" :description="t('hotNews.empty')" />

    <div class="news-list">
      <el-card v-for="item in items" :key="`${item.url ?? item.title}-${item.published_at ?? ''}`" class="news-card" shadow="never">
        <p class="news-time">{{ formatTime(item.published_at) }}</p>
        <h3 class="news-title">{{ item.title }}</h3>
        <p v-if="item.summary" class="news-summary">{{ item.summary }}</p>
        <a v-if="item.url" class="news-link" :href="item.url" target="_blank" rel="noreferrer noopener">
          {{ t('hotNews.openLink') }}
        </a>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.hot-news-page {
  display: grid;
  gap: 0.95rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  font-size: clamp(1.5rem, 2.8vw, 2.05rem);
}

.news-list {
  display: grid;
  gap: 0.75rem;
}

.impact-panel {
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  padding: 0.7rem;
  background: linear-gradient(150deg, rgba(20, 30, 49, 0.9), rgba(9, 16, 28, 0.92));
}

.impact-header h2 {
  margin: 0;
  font-size: 1rem;
}

.impact-list {
  margin-top: 0.55rem;
  display: grid;
  gap: 0.55rem;
}

.impact-item {
  border: 1px solid rgba(123, 197, 255, 0.22);
  border-radius: 10px;
  padding: 0.5rem;
  background: rgba(8, 14, 25, 0.65);
}

.impact-topic {
  margin: 0;
  color: var(--terminal-primary);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.78rem;
}

.impact-row {
  margin: 0.3rem 0 0;
  font-size: 0.83rem;
  color: var(--terminal-muted);
}

.impact-anchor {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  margin-top: 0.35rem;
  color: var(--terminal-text);
}

.impact-anchor__title {
  color: var(--terminal-text);
}

.impact-anchor-switcher {
  margin-top: 0.4rem;
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.impact-candidate-list {
  display: flex;
  flex-direction: column;
  gap: 0.32rem;
  margin-top: 0.35rem;
}

.impact-candidate-label {
  display: inline-block;
}

.impact-candidate-item {
  display: grid;
  gap: 0.5rem;
  border: 1px solid rgba(123, 197, 255, 0.12);
  border-radius: 10px;
  padding: 0.55rem;
  background: rgba(12, 20, 34, 0.72);
}

.impact-candidate-head {
  display: flex;
  gap: 0.6rem;
  justify-content: space-between;
  align-items: flex-start;
}

.impact-candidate-main {
  display: inline-flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  align-items: center;
}

.impact-candidate-industry,
.impact-candidate-breakdown,
.impact-candidate-evidence-time {
  color: var(--terminal-muted);
  font-size: 0.78rem;
}

.impact-candidate-reason {
  margin: 0;
  color: var(--terminal-muted);
  font-size: 0.78rem;
}

.impact-candidate-breakdown {
  margin: 0;
}

.impact-candidate-evidence-list {
  display: grid;
  gap: 0.45rem;
}

.impact-candidate-evidence-card {
  border-radius: 8px;
  border: 1px solid rgba(123, 197, 255, 0.08);
  background: rgba(7, 12, 22, 0.78);
  padding: 0.48rem 0.55rem;
}

.impact-candidate-evidence-head {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  align-items: center;
}

.impact-candidate-evidence-title,
.impact-candidate-evidence-summary {
  margin: 0.25rem 0 0;
}

.impact-candidate-evidence-title {
  color: var(--terminal-text);
  font-size: 0.84rem;
}

.impact-candidate-evidence-summary {
  color: var(--terminal-muted);
  font-size: 0.78rem;
}

.impact-candidate-action {
  color: var(--terminal-primary);
}

.topic-filter-panel {
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  padding: 0.6rem;
  background: rgba(19, 29, 48, 0.66);
}

.topic-filter-label {
  margin: 0;
  color: var(--terminal-muted);
  font-size: 0.78rem;
  font-family: 'IBM Plex Mono', monospace;
}

.topic-filter-list {
  margin-top: 0.45rem;
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.topic-filter-chip {
  border: 1px solid var(--terminal-border);
  border-radius: 999px;
  background: rgba(8, 14, 25, 0.7);
  color: var(--terminal-text);
  font-size: 0.75rem;
  padding: 0.25rem 0.55rem;
  cursor: pointer;
}

.topic-filter-chip.active {
  border-color: color-mix(in srgb, var(--terminal-primary) 65%, var(--terminal-border));
  color: var(--terminal-primary);
}

.news-card {
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
  background: linear-gradient(145deg, rgba(26, 38, 59, 0.96), rgba(14, 23, 37, 0.92));
}

.news-time {
  margin: 0;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.75rem;
}

.news-title {
  margin: 0.35rem 0;
  font-size: 1rem;
}

.news-summary {
  margin: 0;
  color: var(--terminal-muted);
  line-height: 1.5;
}

.news-link {
  display: inline-block;
  margin-top: 0.5rem;
  color: var(--terminal-primary);
  text-decoration: none;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.82rem;
}
</style>
