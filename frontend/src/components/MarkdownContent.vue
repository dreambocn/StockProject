<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const props = defineProps<{
  source: string
}>()

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const defaultLinkOpenRenderer =
  markdown.renderer.rules.link_open ??
  ((
    tokens: any[],
    idx: number,
    options: Record<string, unknown>,
    _env: unknown,
    self: { renderToken: (tokens: any[], idx: number, options: Record<string, unknown>) => string },
  ) => self.renderToken(tokens, idx, options))

markdown.renderer.rules.link_open = (
  tokens: any[],
  idx: number,
  options: Record<string, unknown>,
  env: unknown,
  self: { renderToken: (tokens: any[], idx: number, options: Record<string, unknown>) => string },
) => {
  tokens[idx]?.attrSet('target', '_blank')
  tokens[idx]?.attrSet('rel', 'noreferrer noopener')
  return defaultLinkOpenRenderer(tokens, idx, options, env, self)
}

const renderedHtml = computed(() => {
  const rawHtml = markdown.render(props.source || '')
  return DOMPurify.sanitize(rawHtml, {
    USE_PROFILES: { html: true },
  })
})
</script>

<template>
  <div
    class="markdown-content"
    data-testid="analysis-markdown"
    v-html="renderedHtml"
  />
</template>

<style scoped>
.markdown-content {
  color: #e7f0fb;
  line-height: 1.8;
  font-size: 0.98rem;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3) {
  margin: 0 0 0.75rem;
  color: #f5fbff;
}

.markdown-content :deep(p),
.markdown-content :deep(ul),
.markdown-content :deep(ol),
.markdown-content :deep(blockquote),
.markdown-content :deep(pre) {
  margin: 0 0 0.8rem;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  padding-left: 1.2rem;
}

.markdown-content :deep(code) {
  font-family: 'IBM Plex Mono', monospace;
  padding: 0.1rem 0.25rem;
  border-radius: 6px;
  background: rgba(8, 14, 25, 0.8);
}

.markdown-content :deep(pre code) {
  display: block;
  padding: 0.85rem;
  overflow: auto;
}

.markdown-content :deep(a) {
  color: var(--terminal-primary);
}
</style>
