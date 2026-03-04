<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '../stores/auth'
import { getPasswordStrength, isStrongPassword, PASSWORD_POLICY_MESSAGE_KEY } from '../utils/password'
import { mapApiErrorMessage } from '../utils/apiErrorI18n'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const loading = ref(false)
const sendingCode = ref(false)
const codeCountdown = ref(0)
const successMessage = ref('')
const errorMessage = ref('')
let countdownTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  currentPassword: '',
  newPassword: '',
  emailCode: '',
})

const startCodeCountdown = (seconds: number) => {
  // 倒计时仅用于交互反馈；后端冷却窗口才是最终安全边界。
  codeCountdown.value = seconds
  if (countdownTimer) {
    clearInterval(countdownTimer)
  }

  countdownTimer = setInterval(() => {
    if (codeCountdown.value <= 1) {
      codeCountdown.value = 0
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
      return
    }

    codeCountdown.value -= 1
  }, 1000)
}

const sendEmailCode = async () => {
  if (sendingCode.value || codeCountdown.value > 0) {
    return
  }

  sendingCode.value = true
  successMessage.value = ''
  errorMessage.value = ''
  try {
    // 已登录改密也要求邮箱验证码，形成双重身份校验。
    const result = await authStore.sendChangePasswordEmailCode()
    startCodeCountdown(result.cooldown_in)
  } catch (error) {
    errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
  } finally {
    sendingCode.value = false
  }
}

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
    // 关键提交：当前密码 + 新密码 + 邮箱验证码缺一不可。
    await authStore.changePassword(form.currentPassword, form.newPassword, form.emailCode.trim())
    successMessage.value = t('changePassword.success')
    form.currentPassword = ''
    form.newPassword = ''
    form.emailCode = ''
  } catch (error) {
    errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
  } finally {
    loading.value = false
  }
}

onBeforeUnmount(() => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
  }
})

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
        <el-form-item :label="t('changePassword.emailCode')">
          <el-input v-model="form.emailCode" class="code-input" :placeholder="t('changePassword.emailCodePlaceholder')">
            <template #append>
              <el-button class="code-btn" :class="{ 'is-sending': sendingCode }" native-type="button" :disabled="sendingCode || codeCountdown > 0" @click="sendEmailCode">
                {{ codeCountdown > 0 ? `${codeCountdown}s` : t('changePassword.sendEmailCode') }}
              </el-button>
            </template>
          </el-input>
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

.code-btn {
  min-width: 112px;
  height: 100%;
  margin: 0;
  border: 0 !important;
  border-radius: 0;
  overflow: hidden;
  color: var(--terminal-primary);
  background: color-mix(in srgb, var(--terminal-primary) 14%, transparent);
  box-shadow: none !important;
  transition: background-color 0.2s ease, color 0.2s ease, transform 0.08s ease;
  --el-button-border-color: transparent;
  --el-button-hover-border-color: transparent;
  --el-button-active-border-color: transparent;
  --el-button-disabled-border-color: transparent;
  --el-button-bg-color: color-mix(in srgb, var(--terminal-primary) 14%, transparent);
  --el-button-hover-bg-color: color-mix(in srgb, var(--terminal-primary) 34%, transparent);
  --el-button-active-bg-color: color-mix(in srgb, var(--terminal-primary) 42%, transparent);
  --el-button-disabled-bg-color: color-mix(in srgb, var(--terminal-primary) 10%, transparent);
  --el-button-outline-color: transparent;
}

.code-btn:hover {
  color: #fff;
  background: color-mix(in srgb, var(--terminal-primary) 34%, transparent);
  box-shadow: none;
}

.code-btn:focus,
.code-btn:focus-visible,
.code-btn:active {
  box-shadow: none !important;
  outline: none;
}

.code-btn:active {
  transform: translateY(1px);
}

.code-btn.is-sending {
  position: relative;
  color: transparent !important;
}

.code-btn.is-sending::after {
  content: '';
  position: absolute;
  width: 14px;
  height: 14px;
  left: calc(50% - 7px);
  top: calc(50% - 7px);
  border: 2px solid color-mix(in srgb, var(--terminal-primary) 78%, #d6e4ff);
  border-top-color: transparent;
  border-radius: 50%;
  animation: code-spin 0.85s linear infinite;
}

@keyframes code-spin {
  to {
    transform: rotate(360deg);
  }
}

:deep(.code-input .el-input-group__append) {
  padding: 0;
  border-top: 1px solid var(--terminal-border);
  border-right: 1px solid var(--terminal-border);
  border-bottom: 1px solid var(--terminal-border);
  border-left-color: var(--terminal-border);
  background: color-mix(in srgb, var(--terminal-surface, #10172a) 82%, #0e1728);
  box-shadow: none;
  overflow: hidden;
}

:deep(.code-input .el-input-group__append .el-button),
:deep(.code-input .el-input-group__append .el-button:hover),
:deep(.code-input .el-input-group__append .el-button:focus),
:deep(.code-input .el-input-group__append .el-button:active) {
  border: 0 !important;
  box-shadow: none !important;
}

:deep(.code-input .el-input-group__append .el-button.is-loading::before) {
  inset: 0 !important;
  border-radius: 0 !important;
}
</style>
