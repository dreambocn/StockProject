<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { i18n, setAppLocale, type AppLocale } from './i18n'
import { useAuthStore } from './stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const localeOptions: Array<{ label: string; value: AppLocale }> = [
  { label: '中文', value: 'zh-CN' },
  { label: 'EN', value: 'en-US' },
]

const selectedLocale = computed({
  get: () => i18n.global.locale.value as AppLocale,
  // 统一通过 setAppLocale 写入，确保语言切换与持久化行为一致。
  set: (value: AppLocale) => setAppLocale(value),
})

const localeSliderStyle = computed(() => {
  const activeIndex = localeOptions.findIndex((item) => item.value === selectedLocale.value)
  const safeIndex = activeIndex < 0 ? 0 : activeIndex

  return {
    transform: `translateX(${safeIndex * 100}%)`,
  }
})

const authActionLabel = computed(() =>
  authStore.isAuthenticated ? t('nav.logout') : t('nav.login'),
)

const showAdminNav = computed(() => authStore.isAdmin)

onMounted(async () => {
  // 应用启动时先恢复会话，避免首屏出现登录态闪烁。
  await authStore.initialize()
})

const handleAuthAction = async () => {
  // 顶部按钮根据当前登录态执行“登出”或“去登录”两种分支。
  if (authStore.isAuthenticated) {
    await authStore.logout()
    await router.push('/login')
    return
  }

  await router.push('/login')
}
</script>

<template>
  <div class="terminal-shell">
    <div class="terminal-bg" aria-hidden="true">
      <div class="terminal-grid" />
      <div class="terminal-glow glow-top" />
      <div class="terminal-glow glow-bottom" />
    </div>

    <header class="terminal-header">
      <div>
        <p class="brand-kicker">{{ t('app.brandKicker') }}</p>
        <p class="brand-title">{{ t('app.brandTitle') }}</p>
      </div>

      <nav class="terminal-nav">
        <router-link to="/">{{ t('nav.dashboard') }}</router-link>
        <router-link v-if="showAdminNav" to="/admin">{{ t('nav.admin') }}</router-link>
        <router-link to="/profile">{{ t('nav.profile') }}</router-link>
        <div class="locale-switch" role="group" :aria-label="t('nav.language')">
          <span class="locale-slider" data-testid="locale-slider" :style="localeSliderStyle" />
          <button
            v-for="item in localeOptions"
            :key="item.value"
            type="button"
            class="locale-chip"
            :class="{ active: selectedLocale === item.value }"
            :aria-pressed="selectedLocale === item.value"
            @click="selectedLocale = item.value"
          >
            {{ item.label }}
          </button>
        </div>
        <el-button type="primary" @click="handleAuthAction">{{ authActionLabel }}</el-button>
      </nav>
    </header>

    <main class="terminal-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.terminal-shell {
  position: relative;
  min-height: 100vh;
  padding: 1.3rem;
}

.terminal-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  contain: layout paint style;
  transform: translateZ(0);
}

.terminal-grid,
.terminal-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.terminal-grid {
  background-image:
    linear-gradient(rgba(61, 169, 252, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(61, 169, 252, 0.08) 1px, transparent 1px);
  background-size: 34px 34px;
  opacity: 0.42;
}

.glow-top {
  background: radial-gradient(circle at top right, rgba(61, 169, 252, 0.18), transparent 52%);
  transform: translateZ(0);
}

.glow-bottom {
  background: radial-gradient(circle at bottom left, rgba(247, 181, 0, 0.14), transparent 45%);
  transform: translateZ(0);
}

.terminal-header {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
  border: 1px solid var(--terminal-border);
  border-radius: 14px;
  background: rgba(19, 29, 48, 0.85);
  padding: 0.7rem 1rem;
  box-shadow: var(--terminal-shadow);
}

.brand-kicker {
  margin: 0;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--terminal-primary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-family: 'IBM Plex Mono', monospace;
}

.brand-title {
  margin: 0.2rem 0 0;
  font-weight: 500;
  font-size: 0.82rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
}

.terminal-nav {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.terminal-nav a {
  color: var(--terminal-text);
  text-decoration: none;
  padding: 0.35rem 0.6rem;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: 0.2s ease;
}

.terminal-nav a.router-link-active {
  border-color: var(--terminal-border);
  background: rgba(26, 38, 59, 0.9);
}

.locale-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  padding: 0.2rem;
  border-radius: 999px;
  border: 1px solid var(--terminal-border);
  background: rgba(9, 16, 29, 0.72);
  box-shadow: inset 0 0 0 1px rgba(61, 169, 252, 0.08);
}

.locale-slider {
  position: absolute;
  top: 0.2rem;
  bottom: 0.2rem;
  left: 0.2rem;
  width: calc((100% - 0.4rem) / 2);
  border-radius: 999px;
  background: linear-gradient(135deg, #7bc5ff 0%, #3da9fc 100%);
  box-shadow: 0 8px 20px rgba(61, 169, 252, 0.35);
  transition: transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.locale-chip {
  position: relative;
  z-index: 1;
  border: 0;
  min-width: 3.1rem;
  padding: 0.36rem 0.72rem;
  border-radius: 999px;
  color: var(--terminal-muted);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.74rem;
  letter-spacing: 0.06em;
  background: transparent;
  cursor: pointer;
  transition: color 0.22s ease, background-color 0.22s ease, transform 0.22s ease, box-shadow 0.22s ease;
}

.locale-chip:hover {
  color: var(--terminal-text);
}

.locale-chip:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(61, 169, 252, 0.38);
}

.locale-chip.active {
  color: #061326;
}

.terminal-main {
  position: relative;
  z-index: 1;
  margin: 1rem auto 0;
  max-width: 1040px;
}

@media (max-width: 760px) {
  .terminal-shell {
    padding: 0.75rem;
  }

  .terminal-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .terminal-nav {
    width: 100%;
    justify-content: space-between;
    flex-wrap: wrap;
    row-gap: 0.45rem;
  }
}
</style>
