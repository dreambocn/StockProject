<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const roleLabel = computed(() =>
  authStore.user?.user_level === 'admin' ? t('profile.roleAdmin') : t('profile.roleUser'),
)

onMounted(async () => {
  // 刷新直达个人中心时若内存态为空，主动补拉用户信息。
  if (!authStore.user) {
    // 这里依赖 authStore 内部的鉴权失败处理，避免页面层重复写错误提示。
    await authStore.fetchMe()
  }
})

const goToChangePassword = async () => {
  await router.push('/profile/change-password')
}
</script>

<template>
  <section class="profile-page" v-motion :initial="{ opacity: 0, y: 18 }" :enter="{ opacity: 1, y: 0 }">
    <el-card class="profile-card profile-card--hero" shadow="never">
      <p class="panel-kicker">{{ t('profile.kicker') }}</p>
      <h1>{{ t('profile.title') }}</h1>
      <p class="profile-note">{{ t('profile.overviewNote') }}</p>

      <div class="profile-metrics">
        <article class="profile-metric">
          <span>{{ t('profile.username') }}</span>
          <strong>{{ authStore.user?.username ?? '--' }}</strong>
        </article>
        <article class="profile-metric">
          <span>{{ t('profile.role') }}</span>
          <strong>{{ roleLabel }}</strong>
        </article>
        <article class="profile-metric">
          <span>{{ t('profile.status') }}</span>
          <strong>{{ authStore.user?.is_active ? t('profile.active') : t('profile.inactive') }}</strong>
        </article>
      </div>
    </el-card>

    <div class="profile-grid">
      <el-card data-testid="profile-overview-card" class="profile-card profile-card--panel" shadow="never">
        <p class="panel-kicker panel-kicker--soft">{{ t('profile.overviewTitle') }}</p>
        <el-descriptions :column="1" border class="profile-info">
          <el-descriptions-item :label="t('profile.username')">{{ authStore.user?.username ?? '--' }}</el-descriptions-item>
          <el-descriptions-item :label="t('profile.email')">{{ authStore.user?.email ?? '--' }}</el-descriptions-item>
          <el-descriptions-item :label="t('profile.role')">{{ roleLabel }}</el-descriptions-item>
          <el-descriptions-item :label="t('profile.status')">
            <el-tag :type="authStore.user?.is_active ? 'success' : 'danger'">
              {{ authStore.user?.is_active ? t('profile.active') : t('profile.inactive') }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card data-testid="profile-security-card" class="profile-card profile-card--panel profile-card--security" shadow="never">
        <p class="panel-kicker panel-kicker--warning">{{ t('profile.securityKicker') }}</p>
        <h2>{{ t('profile.securityTitle') }}</h2>
        <p class="section-note">{{ t('profile.securityNote') }}</p>
        <el-button class="action-btn" type="primary" @click="goToChangePassword">{{ t('profile.goChangePassword') }}</el-button>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.profile-page {
  display: grid;
  gap: 1rem;
}

.profile-card {
  border: 1px solid var(--terminal-border);
  border-radius: 16px;
  background: var(--terminal-card-bg);
  box-shadow: var(--terminal-shadow);
}

.profile-card--hero {
  background: var(--terminal-hero-bg);
}

.profile-card--panel {
  height: 100%;
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: var(--terminal-primary);
  letter-spacing: 0.12em;
  font-size: 0.76rem;
  text-transform: uppercase;
}

.panel-kicker--soft {
  color: var(--terminal-text-soft);
}

.panel-kicker--warning {
  color: var(--terminal-warning);
}

h1 {
  margin: 0.45rem 0 0.6rem;
}

h2 {
  margin: 0 0 0.85rem;
}

.profile-note {
  margin: 0;
  color: var(--terminal-text-soft);
  line-height: 1.65;
}

.profile-metrics {
  margin-top: 1rem;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.profile-metric {
  display: grid;
  gap: 0.32rem;
  padding: 0.85rem 0.95rem;
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--terminal-border) 78%, transparent);
  background: color-mix(in srgb, var(--terminal-panel) 88%, var(--terminal-surface) 12%);
}

.profile-metric span {
  color: var(--terminal-text-soft);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.profile-metric strong {
  color: var(--terminal-text);
  font-size: 1.02rem;
}

.profile-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
  gap: 1rem;
}

.profile-info {
  border-color: var(--terminal-border);
}

.section-note {
  margin: 0 0 0.75rem;
  color: var(--terminal-text-soft);
  line-height: 1.65;
}

.action-btn {
  width: 100%;
}

@media (max-width: 900px) {
  .profile-grid,
  .profile-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
