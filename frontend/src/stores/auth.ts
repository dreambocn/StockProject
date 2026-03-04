import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { authApi, type LoginPayload, type UserProfile } from '../api/auth'
import { ApiError } from '../api/http'

const ACCESS_TOKEN_KEY = 'auth.accessToken'
const REFRESH_TOKEN_KEY = 'auth.refreshToken'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)
  const user = ref<UserProfile | null>(null)
  const initialized = ref(false)

  const isAuthenticated = computed(() => Boolean(accessToken.value))
  const isAdmin = computed(() => user.value?.user_level === 'admin')

  const persistTokens = () => {
    // 统一收口 token 持久化，避免不同流程写入策略不一致。
    if (accessToken.value) {
      localStorage.setItem(ACCESS_TOKEN_KEY, accessToken.value)
    } else {
      localStorage.removeItem(ACCESS_TOKEN_KEY)
    }

    if (refreshToken.value) {
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken.value)
    } else {
      localStorage.removeItem(REFRESH_TOKEN_KEY)
    }
  }

  const setTokens = (tokens: { access_token: string; refresh_token: string }) => {
    accessToken.value = tokens.access_token
    refreshToken.value = tokens.refresh_token
    persistTokens()
  }

  const clearAuth = () => {
    // 会话清理必须同时清空内存态与本地存储，防止“伪登录态”。
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    persistTokens()
  }

  const hydrateFromStorage = () => {
    accessToken.value = localStorage.getItem(ACCESS_TOKEN_KEY)
    refreshToken.value = localStorage.getItem(REFRESH_TOKEN_KEY)
  }

  const fetchMe = async () => {
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    user.value = await authApi.me(accessToken.value)
  }

  const refreshSession = async () => {
    if (!refreshToken.value) {
      throw new Error('No refresh token')
    }

    const tokens = await authApi.refresh(refreshToken.value)
    setTokens(tokens)
    // 刷新成功后立即拉取用户信息，确保导航与页面状态同步。
    await fetchMe()
  }

  const initialize = async () => {
    if (initialized.value) {
      return
    }

    hydrateFromStorage()

    if (!accessToken.value) {
      initialized.value = true
      return
    }

    try {
      await fetchMe()
    } catch (error) {
      // 冷启动兜底：access token 过期时尝试 refresh，失败则彻底登出。
      if (error instanceof ApiError && error.status === 401 && refreshToken.value) {
        try {
          await refreshSession()
        } catch {
          clearAuth()
        }
      } else {
        clearAuth()
      }
    } finally {
      initialized.value = true
    }
  }

  const login = async (
    account: string,
    password: string,
    captcha?: Pick<LoginPayload, 'captcha_id' | 'captcha_code'>,
  ) => {
    // 验证码参数按需透传，避免在无验证码场景发送无意义字段。
    const tokens = await authApi.login({ account, password, ...captcha })
    setTokens(tokens)
    await fetchMe()
  }

  const sendRegisterEmailCode = async (email: string) => authApi.sendRegisterEmailCode(email)

  const register = async (
    username: string,
    email: string,
    password: string,
    emailCode: string,
  ) => {
    // 注册成功后直接登录，减少用户额外操作并复用统一会话建立逻辑。
    await authApi.register({ username, email, email_code: emailCode, password })
    await login(username, password)
  }

  const logout = async () => {
    try {
      if (refreshToken.value) {
        // 尽量通知后端撤销 refresh token；即使失败也要执行本地清理。
        await authApi.logout(refreshToken.value)
      }
    } finally {
      clearAuth()
    }
  }

  const sendChangePasswordEmailCode = async () => {
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    return authApi.sendChangePasswordEmailCode(accessToken.value)
  }

  const sendResetPasswordEmailCode = async (email: string) => {
    return authApi.sendResetPasswordEmailCode(email)
  }

  const resetPassword = async (email: string, emailCode: string, newPassword: string) => {
    await authApi.resetPassword({
      email,
      email_code: emailCode,
      new_password: newPassword,
    })
  }

  const changePassword = async (
    currentPassword: string,
    newPassword: string,
    emailCode: string,
  ) => {
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    await authApi.changePassword(accessToken.value, {
      current_password: currentPassword,
      new_password: newPassword,
      email_code: emailCode,
    })
  }

  return {
    accessToken,
    refreshToken,
    user,
    initialized,
    isAuthenticated,
    isAdmin,
    hydrateFromStorage,
    initialize,
    login,
    sendRegisterEmailCode,
    register,
    fetchMe,
    refreshSession,
    sendChangePasswordEmailCode,
    sendResetPasswordEmailCode,
    resetPassword,
    changePassword,
    clearAuth,
    logout,
  }
})
