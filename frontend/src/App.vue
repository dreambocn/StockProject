<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { i18n, setAppLocale, type AppLocale } from './i18n'
import { useAuthStore } from './stores/auth'
import { initializeAppTheme, setAppTheme, themeState, type AppTheme } from './theme'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()
const brandLogoUrl = '/logo-mark.svg'

// 组件级同步可以兜住测试和直接挂载场景，避免只在 main.ts 初始化时才生效。
initializeAppTheme()

const localeOptions: Array<{ label: string; value: AppLocale }> = [
  { label: '中文', value: 'zh-CN' },
  { label: 'EN', value: 'en-US' },
]

const themeOptions = computed<Array<{ label: string; value: AppTheme }>>(() => [
  { label: t('nav.themeLight'), value: 'light' },
  { label: t('nav.themeDark'), value: 'dark' },
])

const selectedLocale = computed({
  get: () => i18n.global.locale.value as AppLocale,
  // 统一通过 setAppLocale 写入，确保语言切换与持久化行为一致。
  set: (value: AppLocale) => setAppLocale(value),
})

const selectedTheme = computed({
  get: () => themeState.value,
  // 主题切换统一通过 setAppTheme 收口，保证根节点属性与本地缓存同步。
  set: (value: AppTheme) => setAppTheme(value),
})

const localeSliderStyle = computed(() => {
  const activeIndex = localeOptions.findIndex((item) => item.value === selectedLocale.value)
  const safeIndex = activeIndex < 0 ? 0 : activeIndex

  return {
    transform: `translateX(${safeIndex * 100}%)`,
  }
})

const themeSliderStyle = computed(() => {
  const activeIndex = themeOptions.value.findIndex((item) => item.value === selectedTheme.value)
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
    // 登出后统一回登录页，避免停留在需要鉴权的路由。
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
      <div class="brand-block">
        <img class="brand-logo" :src="brandLogoUrl" alt="脉策图标" />
        <div>
        <p class="brand-kicker">{{ t('app.brandKicker') }}</p>
        <p class="brand-title">{{ t('app.brandTitle') }}</p>
        </div>
      </div>

      <nav class="terminal-nav">
        <router-link to="/">{{ t('nav.dashboard') }}</router-link>
        <router-link to="/news/hot">{{ t('nav.hotNews') }}</router-link>
        <router-link to="/policy/documents">{{ t('nav.policy') }}</router-link>
        <router-link to="/watchlist">{{ t('nav.watchlist') }}</router-link>
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
        <div class="theme-switch" role="group" :aria-label="t('nav.theme')">
          <span class="theme-slider" data-testid="theme-slider" :style="themeSliderStyle" />
          <button
            v-for="item in themeOptions"
            :key="item.value"
            :data-testid="`theme-chip-${item.value}`"
            type="button"
            class="theme-chip"
            :class="{ active: selectedTheme === item.value }"
            :aria-pressed="selectedTheme === item.value"
            @click="selectedTheme = item.value"
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
    linear-gradient(var(--terminal-grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--terminal-grid-line) 1px, transparent 1px);
  background-size: 34px 34px;
  opacity: var(--terminal-grid-opacity);
}

.glow-top {
  background: var(--terminal-glow-top);
  transform: translateZ(0);
}

.glow-bottom {
  background: var(--terminal-glow-bottom);
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
  background: var(--terminal-header-bg);
  padding: 0.7rem 1rem;
  box-shadow: var(--terminal-shadow);
  backdrop-filter: blur(18px);
}

.brand-block {
  display: inline-flex;
  align-items: center;
  gap: 0.85rem;
}

.brand-logo {
  width: 2.6rem;
  height: 2.6rem;
  border-radius: 0.95rem;
  flex-shrink: 0;
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
  font-weight: 700;
  font-size: 1.1rem;
  letter-spacing: 0.06em;
  color: var(--terminal-text);
  font-family: 'IBM Plex Sans', 'Microsoft YaHei', sans-serif;
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
  background: var(--terminal-nav-active-bg);
}

.locale-switch,
.theme-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  padding: 0.2rem;
  border-radius: 999px;
  border: 1px solid var(--terminal-border);
  background: var(--terminal-pill-bg);
  box-shadow: inset 0 0 0 1px var(--terminal-pill-shadow);
}

.locale-slider,
.theme-slider {
  position: absolute;
  top: 0.2rem;
  bottom: 0.2rem;
  left: 0.2rem;
  width: calc((100% - 0.4rem) / 2);
  border-radius: 999px;
  background: var(--terminal-pill-active-bg);
  box-shadow: var(--terminal-pill-active-shadow);
  transition: transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.locale-chip,
.theme-chip {
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

.locale-chip:hover,
.theme-chip:hover {
  color: var(--terminal-text);
}

.locale-chip:focus-visible,
.theme-chip:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--terminal-focus-ring);
}

.locale-chip.active,
.theme-chip.active {
  color: var(--terminal-pill-active-text);
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
