<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { authApi } from '../api/auth'
import { ApiError } from '../api/http'
import { useAuthStore } from '../stores/auth'
import { mapApiErrorMessage } from '../utils/apiErrorI18n'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const form = reactive({
  account: '',
  password: '',
})

const loading = ref(false)
const errorMessage = ref('')
const captchaRequired = ref(false)
const captchaId = ref('')
const captchaCode = ref('')
const captchaImage = ref('')

const refreshCaptcha = async () => {
  // 验证码由后端生成并缓存答案，前端仅持有 challenge id + 图片。
  const challenge = await authApi.getCaptchaChallenge()
  captchaId.value = challenge.captcha_id
  captchaImage.value = challenge.image_base64
}

const parseCaptchaDetail = (error: ApiError) => {
  if (!error.payload || typeof error.payload !== 'object' || !('detail' in error.payload)) {
    return null
  }

  const detail = (error.payload as { detail: unknown }).detail
  if (!detail || typeof detail !== 'object' || !('captcha_required' in detail)) {
    return null
  }

  return detail as { message?: string; captcha_required?: boolean }
}

const submitLogin = async () => {
  errorMessage.value = ''
  loading.value = true
  try {
    // 仅在被风控要求时才提交验证码字段，减少无关请求负担。
    await authStore.login(form.account, form.password, {
      captcha_id: captchaRequired.value ? captchaId.value : undefined,
      captcha_code: captchaRequired.value ? captchaCode.value.trim().toUpperCase() : undefined,
    })
    captchaRequired.value = false
    captchaId.value = ''
    captchaCode.value = ''
    captchaImage.value = ''
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch (error) {
    if (error instanceof ApiError) {
      const captchaDetail = parseCaptchaDetail(error)
      if (captchaDetail?.captcha_required) {
        // 当后端返回 captcha_required，前端立刻切换到验证码登录分支。
        captchaRequired.value = true
        await refreshCaptcha()
      }
    }

    errorMessage.value = mapApiErrorMessage(error, t, 'errors.fallback')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="auth-page" v-motion :initial="{ opacity: 0, y: 18 }" :enter="{ opacity: 1, y: 0 }">
    <article class="auth-panel">
      <p class="panel-kicker">{{ t('auth.login.kicker') }}</p>
      <h1>{{ t('auth.login.title') }}</h1>
      <p class="panel-note">{{ t('auth.login.note') }}</p>

      <el-form label-position="top" @submit.prevent="submitLogin">
        <el-form-item :label="t('auth.login.accountLabel')">
          <el-input v-model="form.account" :placeholder="t('auth.login.accountPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('auth.login.passwordLabel')">
          <el-input v-model="form.password" type="password" show-password :placeholder="t('auth.login.passwordPlaceholder')" />
        </el-form-item>
        <transition name="captcha-fade">
          <div v-if="captchaRequired" class="captcha-wrap">
            <el-form-item :label="t('auth.login.captchaLabel')">
              <el-input v-model="captchaCode" :placeholder="t('auth.login.captchaPlaceholder')" />
            </el-form-item>
            <div class="captcha-row">
              <img
                v-if="captchaImage"
                class="captcha-image"
                :src="`data:image/png;base64,${captchaImage}`"
                alt="captcha"
              />
              <el-button text @click="refreshCaptcha">{{ t('auth.login.refreshCaptcha') }}</el-button>
            </div>
          </div>
        </transition>
        <el-alert v-if="errorMessage" class="form-alert" :title="errorMessage" type="error" show-icon :closable="false" />
        <el-button class="submit-btn" native-type="submit" type="primary" :loading="loading">
          {{ t('auth.login.submit') }}
        </el-button>
      </el-form>

      <p class="jump-link">
        {{ t('auth.login.noAccount') }}<router-link to="/register">{{ t('auth.login.goRegister') }}</router-link>
      </p>
      <p class="jump-link secondary">
        <router-link to="/reset-password">{{ t('auth.login.forgotPassword') }}</router-link>
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
  color: var(--terminal-primary);
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

.form-alert {
  margin-bottom: 0.75rem;
}

.captcha-wrap {
  margin-bottom: 0.75rem;
}

.captcha-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.7rem;
}

.captcha-image {
  width: 160px;
  height: 56px;
  border: 1px solid var(--terminal-border);
  border-radius: 8px;
  background: #f4f8ff;
}

.captcha-fade-enter-active,
.captcha-fade-leave-active {
  transition: opacity 0.2s ease;
}

.captcha-fade-enter-from,
.captcha-fade-leave-to {
  opacity: 0;
}

.jump-link {
  margin: 0.9rem 0 0;
  color: var(--terminal-muted);
  text-align: right;
}

.jump-link a {
  color: var(--terminal-primary);
}

.jump-link.secondary {
  margin-top: 0.35rem;
}
</style>
