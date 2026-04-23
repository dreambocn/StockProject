<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const adminEntries = [
  {
    key: 'users',
    to: '/admin/users',
    icon: '👥',
    titleKey: 'adminConsole.entries.users.title',
    noteKey: 'adminConsole.entries.users.note',
  },
  {
    key: 'stocks',
    to: '/admin/stocks',
    icon: '📈',
    titleKey: 'adminConsole.entries.stocks.title',
    noteKey: 'adminConsole.entries.stocks.note',
  },
  {
    key: 'jobs',
    to: '/admin/jobs',
    icon: '🛰️',
    titleKey: 'adminConsole.entries.jobs.title',
    noteKey: 'adminConsole.entries.jobs.note',
  },
  {
    key: 'policy',
    to: '/policy/documents',
    icon: '📜',
    titleKey: 'adminConsole.entries.policy.title',
    noteKey: 'adminConsole.entries.policy.note',
  },
]
// 后台入口使用配置数组渲染，便于后续扩展时保持结构一致。
</script>

<template>
  <section
    class="admin-console-page"
    v-motion
    :initial="{ opacity: 0, y: 16 }"
    :enter="{ opacity: 1, y: 0 }"
  >
    <header class="console-header">
      <p class="panel-kicker">{{ t('adminConsole.kicker') }}</p>
      <h1>{{ t('adminConsole.title') }}</h1>
      <p class="section-note">{{ t('adminConsole.note') }}</p>
    </header>

    <div class="entry-grid">
      <router-link
        v-for="entry in adminEntries"
        :key="entry.key"
        :to="entry.to"
        class="entry-card"
      >
        <p class="entry-icon">{{ entry.icon }}</p>
        <h2>{{ t(entry.titleKey) }}</h2>
        <p class="entry-note">{{ t(entry.noteKey) }}</p>
        <span class="entry-action">{{ t('adminConsole.enter') }}</span>
      </router-link>
    </div>
  </section>
</template>

<style scoped>
.admin-console-page {
  display: grid;
  gap: 1rem;
}

.console-header {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  padding: 1rem 1.1rem;
  background: var(--terminal-hero-bg);
  box-shadow: var(--terminal-shadow);
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
  margin: 0.42rem 0 0.3rem;
}

.section-note {
  margin: 0;
  color: var(--terminal-muted);
}

.entry-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.entry-card {
  text-decoration: none;
  color: var(--terminal-text);
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  padding: 1rem;
  display: grid;
  gap: 0.45rem;
  background: var(--terminal-card-elevated-bg);
  transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
  box-shadow: var(--terminal-shadow);
}

.entry-card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--terminal-primary) 46%, var(--terminal-border));
  box-shadow: 0 14px 32px color-mix(in srgb, var(--terminal-primary) 12%, transparent);
}

.entry-icon {
  margin: 0;
  font-size: 1.2rem;
}

h2 {
  margin: 0;
}

.entry-note {
  margin: 0;
  color: var(--terminal-muted);
  line-height: 1.45;
}

.entry-action {
  font-family: 'IBM Plex Mono', monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--terminal-primary);
  font-size: 0.76rem;
}

@media (max-width: 860px) {
  .entry-grid {
    grid-template-columns: 1fr;
  }
}
</style>
