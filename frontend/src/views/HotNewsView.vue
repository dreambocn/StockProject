<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { newsApi, type HotNewsItem, type MacroImpactProfile } from '../api/news'
import { ApiError } from '../api/http'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const impactLoading = ref(false)
const errorMessage = ref('')
const items = ref<HotNewsItem[]>([])
const impactProfiles = ref<MacroImpactProfile[]>([])
const selectedTopic = ref('all')

const topicOptions = [
  'all',
  'geopolitical_conflict',
  'monetary_policy',
  'commodity_supply',
  'regulation_policy',
  'other',
] as const

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

const selectTopic = async (topic: string) => {
  if (selectedTopic.value === topic) {
    return
  }
  selectedTopic.value = topic
  await Promise.all([loadHotNews(), loadImpactProfiles()])
}

onMounted(async () => {
  await Promise.all([loadHotNews(), loadImpactProfiles()])
})

const goToAnalysis = async (tsCode: string, topic: string) => {
  await router.push({
    path: '/analysis',
    query: {
      ts_code: tsCode,
      topic,
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
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.assets') }}:</strong> {{ profile.affected_assets.join(' / ') }}</p>
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.beneficiarySectors') }}:</strong> {{ profile.beneficiary_sectors.join(' / ') }}</p>
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.pressureSectors') }}:</strong> {{ profile.pressure_sectors.join(' / ') }}</p>
          <p class="impact-row"><strong>{{ t('hotNews.impactPanel.targets') }}:</strong> {{ profile.a_share_targets.join(' / ') }}</p>
          <p class="impact-row">
            <strong>{{ t('hotNews.impactPanel.candidates') }}:</strong>
            <span v-if="profile.a_share_candidates.length > 0" class="impact-candidate-list">
              <span
                v-for="candidate in profile.a_share_candidates"
                :key="candidate.ts_code"
                class="impact-candidate-item"
              >
                <span>{{ `${candidate.name}(${candidate.ts_code})` }}</span>
                <el-button
                  text
                  size="small"
                  class="impact-candidate-action"
                  @click="goToAnalysis(candidate.ts_code, profile.topic)"
                >
                  {{ t('hotNews.enterAnalysis') }}
                </el-button>
              </span>
            </span>
            <span v-else>--</span>
          </p>
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

.impact-candidate-list {
  display: inline-flex;
  flex-direction: column;
  gap: 0.32rem;
}

.impact-candidate-item {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.impact-candidate-action {
  padding: 0;
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
