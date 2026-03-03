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

  const persistTokens = () => {
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
    const tokens = await authApi.login({ account, password, ...captcha })
    setTokens(tokens)
    await fetchMe()
  }

  const register = async (username: string, email: string, password: string) => {
    await authApi.register({ username, email, password })
    await login(username, password)
  }

  const logout = async () => {
    try {
      if (refreshToken.value) {
        await authApi.logout(refreshToken.value)
      }
    } finally {
      clearAuth()
    }
  }

  const changePassword = async (currentPassword: string, newPassword: string) => {
    if (!accessToken.value) {
      throw new Error('No access token')
    }

    await authApi.changePassword(accessToken.value, {
      current_password: currentPassword,
      new_password: newPassword,
    })
  }

  return {
    accessToken,
    refreshToken,
    user,
    initialized,
    isAuthenticated,
    hydrateFromStorage,
    initialize,
    login,
    register,
    fetchMe,
    refreshSession,
    changePassword,
    clearAuth,
    logout,
  }
})
