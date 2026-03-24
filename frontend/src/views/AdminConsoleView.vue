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
    key: 'evaluations',
    to: '/admin/evaluations',
    icon: '🧪',
    titleKey: 'adminConsole.entries.evaluations.title',
    noteKey: 'adminConsole.entries.evaluations.note',
  },
]
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
  background:
    radial-gradient(circle at top right, rgba(122, 206, 255, 0.18), transparent 60%),
    linear-gradient(145deg, rgba(18, 29, 50, 0.96), rgba(8, 16, 30, 0.97));
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
  background:
    radial-gradient(circle at 85% 18%, rgba(247, 181, 0, 0.16), transparent 44%),
    linear-gradient(145deg, rgba(20, 32, 54, 0.96), rgba(9, 17, 31, 0.98));
  transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
}

.entry-card:hover {
  transform: translateY(-2px);
  border-color: rgba(123, 197, 255, 0.55);
  box-shadow: 0 14px 32px rgba(6, 12, 24, 0.36);
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
  color: #7bc5ff;
  font-size: 0.76rem;
}

@media (max-width: 860px) {
  .entry-grid {
    grid-template-columns: 1fr;
  }
}
</style>
