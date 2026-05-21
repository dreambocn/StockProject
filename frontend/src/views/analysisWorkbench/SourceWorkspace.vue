<script setup lang="ts">
import type { AnalysisReportResponse, AnalysisSourceItem } from '../../api/analysis'

type StructuredSourceItem = NonNullable<AnalysisReportResponse['structured_sources']>[number]
type WebSourceItem = NonNullable<AnalysisReportResponse['web_sources']>[number]

defineProps<{
  structuredSources: StructuredSourceItem[]
  runtimeMeta: string[]
  sourceItems: AnalysisSourceItem[]
  webSources: WebSourceItem[]
  dataMissingText: string
  inputSourcesTitle: string
  reportMetaTitle: string
  sourceWorkspaceTitle: string
  webSourcesTitle: string
  webSourceMissingTimeText: string
  formatStructuredSourceProvider: (provider: string | null | undefined) => string | null | undefined
  formatDateTime: (value: string | null | undefined) => string
  translateSourceKind: (value: AnalysisSourceItem['source_kind']) => string
  translateSourceQuality: (value: string | null | undefined) => string
  translateWebSourceMetadataStatus: (value: string | null | undefined) => string
}>()

defineEmits<{
  focusSource: [sourceItem: AnalysisSourceItem, event: Event]
}>()
</script>

<template>
  <div class="analysis-sources-workspace">
    <section v-if="structuredSources.length > 0" class="analysis-sources-section">
      <p class="analysis-sources-section__title">{{ inputSourcesTitle }}</p>
      <div class="analysis-source-evidence">
        <span
          v-for="sourceItem in structuredSources"
          :key="`${sourceItem.provider}-${sourceItem.count}`"
          class="analysis-token"
        >
          {{ `${formatStructuredSourceProvider(sourceItem.provider) ?? dataMissingText} × ${sourceItem.count ?? 0}` }}
        </span>
      </div>
    </section>

    <section v-if="runtimeMeta.length > 0" class="analysis-sources-section">
      <p class="analysis-sources-section__title">{{ reportMetaTitle }}</p>
      <div class="analysis-runtime-meta">
        <span v-for="metaItem in runtimeMeta" :key="metaItem">{{ metaItem }}</span>
      </div>
    </section>

    <section v-if="sourceItems.length > 0" class="analysis-sources-section">
      <p class="analysis-sources-section__title">{{ sourceWorkspaceTitle }}</p>
      <div class="analysis-web-source-list">
        <component
          :is="sourceItem.url ? 'a' : 'button'"
          v-for="sourceItem in sourceItems"
          :key="sourceItem.id"
          class="analysis-web-source-item analysis-source-item"
          :data-testid="`analysis-source-item-${sourceItem.id}`"
          :href="sourceItem.url || undefined"
          target="_blank"
          rel="noreferrer noopener"
          type="button"
          @click="$emit('focusSource', sourceItem, $event)"
        >
          <strong>{{ sourceItem.title }}</strong>
          <span>
            {{ translateSourceKind(sourceItem.source_kind) }}
            ·
            {{ sourceItem.source_name || sourceItem.domain || dataMissingText }}
          </span>
          <span>
            {{ sourceItem.published_at ? formatDateTime(sourceItem.published_at) : webSourceMissingTimeText }}
          </span>
          <span v-if="sourceItem.domain && sourceItem.domain !== sourceItem.source_name">
            {{ sourceItem.domain }}
          </span>
          <span class="analysis-token">
            {{ translateSourceQuality(sourceItem.quality_status) }}
          </span>
          <span v-if="sourceItem.snippet">{{ sourceItem.snippet }}</span>
        </component>
      </div>
    </section>

    <section v-if="webSources.length > 0" class="analysis-sources-section">
      <p class="analysis-sources-section__title">{{ webSourcesTitle }}</p>
      <div class="analysis-web-source-list">
        <a
          v-for="webSource in webSources"
          :key="webSource.url || webSource.title"
          class="analysis-web-source-item"
          :href="webSource.url || undefined"
          target="_blank"
          rel="noreferrer noopener"
        >
          <strong>{{ webSource.title || webSource.url || dataMissingText }}</strong>
          <span>
            {{ webSource.source || webSource.domain || dataMissingText }}
          </span>
          <span>
            {{ webSource.published_at ? formatDateTime(webSource.published_at) : webSourceMissingTimeText }}
          </span>
          <span v-if="webSource.domain && webSource.domain !== webSource.source">
            {{ webSource.domain }}
          </span>
          <span>
            {{ translateWebSourceMetadataStatus(webSource.metadata_status) }}
          </span>
          <span v-if="webSource.snippet">{{ webSource.snippet }}</span>
        </a>
      </div>
    </section>
  </div>
</template>

<style scoped>
.analysis-sources-workspace {
  display: grid;
  gap: 1rem;
}

.analysis-sources-section {
  display: grid;
  gap: 0.6rem;
  padding: 0.85rem 0.9rem;
  border-radius: 16px;
  border: 1px solid rgba(123, 197, 255, 0.1);
  background: color-mix(in srgb, var(--terminal-panel) 92%, var(--terminal-surface) 8%);
}

.analysis-sources-section__title {
  margin: 0;
  color: var(--terminal-text);
  font-size: 0.9rem;
  font-weight: 600;
}

.analysis-source-evidence,
.analysis-runtime-meta {
  margin-bottom: 0.8rem;
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.analysis-token {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  border: 1px solid rgba(123, 197, 255, 0.16);
  background: var(--terminal-chip-bg);
  color: var(--terminal-primary);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
}

.analysis-web-source-list {
  margin-bottom: 0.8rem;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem;
}

.analysis-web-source-item {
  display: grid;
  gap: 0.2rem;
  padding: 0.75rem 0.85rem;
  border-radius: 12px;
  border: 1px solid rgba(123, 197, 255, 0.14);
  background: color-mix(in srgb, var(--terminal-panel) 94%, var(--terminal-surface) 6%);
  color: color-mix(in srgb, var(--terminal-text) 82%, var(--terminal-muted) 18%);
  text-decoration: none;
}

.analysis-web-source-item strong {
  color: var(--terminal-text);
}

.analysis-web-source-item span {
  color: var(--terminal-text-body);
}

.analysis-source-item {
  width: 100%;
  text-align: left;
  cursor: pointer;
  font: inherit;
}

@media (max-width: 760px) {
  .analysis-web-source-list {
    grid-template-columns: 1fr;
  }
}
</style>
