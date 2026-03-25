<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()

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
    <el-card class="profile-card" shadow="never">
      <p class="panel-kicker">{{ t('profile.kicker') }}</p>
      <h1>{{ t('profile.title') }}</h1>
      <el-descriptions :column="1" border class="profile-info">
        <el-descriptions-item :label="t('profile.username')">{{ authStore.user?.username }}</el-descriptions-item>
        <el-descriptions-item :label="t('profile.email')">{{ authStore.user?.email }}</el-descriptions-item>
        <el-descriptions-item :label="t('profile.status')">
          <el-tag :type="authStore.user?.is_active ? 'success' : 'danger'">
            {{ authStore.user?.is_active ? t('profile.active') : t('profile.inactive') }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="profile-card" shadow="never">
      <h2>{{ t('profile.securityTitle') }}</h2>
      <p class="section-note">{{ t('profile.securityNote') }}</p>
      <el-button class="action-btn" type="primary" @click="goToChangePassword">{{ t('profile.goChangePassword') }}</el-button>
    </el-card>
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
  background: linear-gradient(145deg, rgba(19, 29, 48, 0.95), rgba(11, 18, 32, 0.96));
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: var(--terminal-primary);
  letter-spacing: 0.12em;
  font-size: 0.76rem;
  text-transform: uppercase;
}

h1 {
  margin: 0.45rem 0 1rem;
}

h2 {
  margin: 0 0 0.85rem;
}

.profile-info {
  border-color: var(--terminal-border);
}

.section-note {
  margin: 0 0 0.75rem;
  color: var(--terminal-muted);
}

.action-btn {
  width: 100%;
}
</style>
