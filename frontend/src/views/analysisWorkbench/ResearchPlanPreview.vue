<script setup lang="ts">
import type { ResearchPlanResponse } from '../../api/analysis'

defineProps<{
  plan: ResearchPlanResponse
  streaming: boolean
}>()

defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<template>
  <el-card
    class="analysis-panel analysis-research-plan"
    data-testid="analysis-research-plan-preview"
  >
    <div class="analysis-panel__header">
      <div>
        <p class="analysis-panel__eyebrow">研究计划预览</p>
        <h2 class="analysis-panel__title">{{ plan.summary }}</h2>
      </div>
      <span class="analysis-token">
        {{ plan.web_search_recommended ? '建议联网增强' : '本地证据优先' }}
      </span>
    </div>
    <div class="analysis-source-evidence">
      <span
        v-for="bucket in plan.focus_buckets"
        :key="bucket.key"
        class="analysis-token"
      >
        {{ `${bucket.label} × ${bucket.count}` }}
      </span>
    </div>
    <ul class="analysis-risk-list">
      <li
        v-for="question in plan.priority_questions"
        :key="question"
      >
        {{ question }}
      </li>
    </ul>
    <div class="analysis-hero__secondary-actions">
      <el-button type="primary" :loading="streaming" @click="$emit('confirm')">
        确认并生成
      </el-button>
      <el-button plain @click="$emit('cancel')">
        稍后再说
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 0.9rem;
}

.analysis-panel__eyebrow,
.analysis-token {
  font-family: 'IBM Plex Mono', monospace;
}

.analysis-panel__eyebrow {
  margin: 0 0 0.32rem;
  font-size: 0.76rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--terminal-primary);
}

.analysis-panel__title {
  margin: 0;
  color: var(--terminal-text);
  font-size: 1.05rem;
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
  font-size: 0.74rem;
}

.analysis-source-evidence {
  margin-bottom: 0.8rem;
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.analysis-risk-list {
  list-style: none;
  margin: 0 0 0.9rem;
  padding: 0;
  display: grid;
  gap: 0.65rem;
}

.analysis-risk-list li {
  border-left: 2px solid rgba(247, 181, 0, 0.72);
  padding-left: 0.75rem;
  color: var(--terminal-text-body);
  line-height: 1.6;
}

.analysis-hero__secondary-actions {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

@media (max-width: 760px) {
  .analysis-panel__header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
