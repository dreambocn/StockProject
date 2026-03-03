<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '../stores/auth'
import { getPasswordStrength, isStrongPassword, PASSWORD_POLICY_MESSAGE_KEY } from '../utils/password'
import { mapApiErrorMessage } from '../utils/apiErrorI18n'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const loading = ref(false)
const successMessage = ref('')
const errorMessage = ref('')

const form = reactive({
  currentPassword: '',
  newPassword: '',
})

const strength = computed(() => getPasswordStrength(form.newPassword))
const strengthLabel = computed(() => {
  if (strength.value === 'none') return t('password.none')
  if (strength.value === 'strong') return t('password.strong')
  if (strength.value === 'medium') return t('password.medium')
  return t('password.weak')
})
const strengthPercent = computed(() => {
  if (strength.value === 'none') return 0
  if (strength.value === 'strong') return 100
  if (strength.value === 'medium') return 66
  return 33
})
const strengthStatus = computed(() => {
  if (strength.value === 'none') return undefined
  if (strength.value === 'strong') return 'success'
  if (strength.value === 'medium') return 'warning'
  return 'exception'
})

const submitChangePassword = async () => {
  loading.value = true
  successMessage.value = ''
  errorMessage.value = ''

  if (!isStrongPassword(form.newPassword)) {
    errorMessage.value = t(PASSWORD_POLICY_MESSAGE_KEY)
    loading.value = false
    return
  }

  try {
    await authStore.changePassword(form.currentPassword, form.newPassword)
    successMessage.value = t('changePassword.success')
    form.currentPassword = ''
    form.newPassword = ''
  } catch (error) {
    errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
  } finally {
    loading.value = false
  }
}

const backToProfile = async () => {
  await router.push('/profile')
}
</script>

<template>
  <section class="profile-page" v-motion :initial="{ opacity: 0, y: 18 }" :enter="{ opacity: 1, y: 0 }">
    <el-card class="profile-card" shadow="never">
      <div class="title-row">
        <h1>{{ t('changePassword.title') }}</h1>
        <el-button text @click="backToProfile">{{ t('changePassword.backToProfile') }}</el-button>
      </div>
      <el-form label-position="top" @submit.prevent="submitChangePassword">
        <el-form-item :label="t('changePassword.currentPassword')">
          <el-input v-model="form.currentPassword" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('changePassword.newPassword')">
          <el-input v-model="form.newPassword" type="password" show-password :placeholder="t('changePassword.newPasswordPlaceholder')" />
        </el-form-item>

        <transition name="strength-fade">
          <div v-if="strength !== 'none'" class="strength-wrap">
            <span>{{ t('changePassword.strength') }}：{{ strengthLabel }}</span>
            <el-progress :percentage="strengthPercent" :status="strengthStatus" :show-text="false" />
          </div>
        </transition>

        <el-alert v-if="successMessage" class="form-alert" :title="successMessage" type="success" show-icon :closable="false" />
        <el-alert v-if="errorMessage" class="form-alert" :title="errorMessage" type="error" show-icon :closable="false" />
        <el-button class="submit-btn" type="primary" native-type="submit" :loading="loading">
          {{ t('changePassword.submit') }}
        </el-button>
      </el-form>
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

.title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
  margin-bottom: 0.6rem;
}

h1 {
  margin: 0;
}

.strength-wrap {
  margin-bottom: 0.7rem;
  color: var(--terminal-muted);
}

.strength-fade-enter-active,
.strength-fade-leave-active {
  transition: opacity 0.2s ease;
}

.strength-fade-enter-from,
.strength-fade-leave-to {
  opacity: 0;
}

.form-alert {
  margin-bottom: 0.75rem;
}

.submit-btn {
  width: 100%;
}
</style>
