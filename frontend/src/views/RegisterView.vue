<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '../stores/auth'
import {
  getPasswordStrength,
  isStrongPassword,
  PASSWORD_POLICY_MESSAGE_KEY,
} from '../utils/password'
import { mapApiErrorMessage } from '../utils/apiErrorI18n'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const form = reactive({
  username: '',
  email: '',
  emailCode: '',
  password: '',
  confirmPassword: '',
})

const loading = ref(false)
const sendingCode = ref(false)
const codeCountdown = ref(0)
const errorMessage = ref('')
let countdownTimer: ReturnType<typeof setInterval> | null = null

const startCodeCountdown = (seconds: number) => {
  // 倒计时作为前端节流提示；真实防刷仍以后端冷却校验为准。
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
  if (!form.email || sendingCode.value || codeCountdown.value > 0) {
    return
  }

  sendingCode.value = true
  errorMessage.value = ''
  try {
    const result = await authStore.sendRegisterEmailCode(form.email)
    startCodeCountdown(result.cooldown_in)
  } catch (error) {
    errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
  } finally {
    sendingCode.value = false
  }
}

onBeforeUnmount(() => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
  }
})

const strength = computed(() => getPasswordStrength(form.password))
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

const submitRegister = async () => {
  errorMessage.value = ''

  if (form.password !== form.confirmPassword) {
    errorMessage.value = t('auth.register.mismatch')
    return
  }

  if (!isStrongPassword(form.password)) {
    errorMessage.value = t(PASSWORD_POLICY_MESSAGE_KEY)
    return
  }

  loading.value = true
  try {
    // 关键链路：注册请求必须携带邮箱验证码，后端才允许创建账号。
    await authStore.register(form.username, form.email, form.password, form.emailCode.trim())
    await router.push('/')
  } catch (error) {
    errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="auth-page" v-motion :initial="{ opacity: 0, y: 18 }" :enter="{ opacity: 1, y: 0 }">
    <article class="auth-panel">
      <p class="panel-kicker">{{ t('auth.register.kicker') }}</p>
      <h1>{{ t('auth.register.title') }}</h1>
      <p class="panel-note">{{ t('auth.register.note') }}</p>

      <el-form label-position="top" @submit.prevent="submitRegister">
        <el-form-item :label="t('auth.register.usernameLabel')">
          <el-input v-model="form.username" :placeholder="t('auth.register.usernamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('auth.register.emailLabel')">
          <el-input v-model="form.email" :placeholder="t('auth.register.emailPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('auth.register.emailCodeLabel')">
          <el-input v-model="form.emailCode" class="code-input" :placeholder="t('auth.register.emailCodePlaceholder')">
            <template #append>
              <el-button class="code-btn" :class="{ 'is-sending': sendingCode }" native-type="button" :disabled="sendingCode || !form.email || codeCountdown > 0" @click="sendEmailCode">
                {{ codeCountdown > 0 ? `${codeCountdown}s` : t('auth.register.sendEmailCode') }}
              </el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item :label="t('auth.register.passwordLabel')">
          <el-input v-model="form.password" type="password" show-password :placeholder="t('auth.register.passwordPlaceholder')" />
        </el-form-item>
        <transition name="strength-fade">
          <div v-if="strength !== 'none'" class="strength-wrap">
            <span>{{ t('changePassword.strength') }}：{{ strengthLabel }}</span>
            <el-progress :percentage="strengthPercent" :status="strengthStatus" :show-text="false" />
          </div>
        </transition>
        <el-form-item :label="t('auth.register.confirmPasswordLabel')">
          <el-input v-model="form.confirmPassword" type="password" show-password :placeholder="t('auth.register.confirmPasswordPlaceholder')" />
        </el-form-item>
        <el-alert v-if="errorMessage" class="form-alert" :title="errorMessage" type="error" show-icon :closable="false" />
        <el-button class="submit-btn" native-type="submit" type="primary" :loading="loading">
          {{ t('auth.register.submit') }}
        </el-button>
      </el-form>

      <p class="jump-link">
        {{ t('auth.register.hasAccount') }}<router-link to="/login">{{ t('auth.register.goLogin') }}</router-link>
      </p>
    </article>
  </section>
</template>

<style scoped>
.auth-page {
  max-width: 560px;
  margin: 0 auto;
}

.auth-panel {
  border: 1px solid var(--terminal-border);
  background: linear-gradient(145deg, rgba(19, 29, 48, 0.95), rgba(11, 18, 32, 0.96));
  border-radius: 16px;
  padding: 1.3rem;
  box-shadow: var(--terminal-shadow);
}

.panel-kicker {
  margin: 0;
  font-family: 'IBM Plex Mono', monospace;
  color: var(--terminal-warning);
  letter-spacing: 0.12em;
  font-size: 0.76rem;
  text-transform: uppercase;
}

h1 {
  margin: 0.45rem 0;
}

.panel-note {
  margin: 0 0 1rem;
  color: var(--terminal-muted);
}

.submit-btn {
  width: 100%;
  margin-top: 0.25rem;
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

.jump-link {
  margin: 0.9rem 0 0;
  color: var(--terminal-muted);
  text-align: right;
}

.jump-link a {
  color: var(--terminal-primary);
}
</style>
