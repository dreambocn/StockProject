import { requestJson } from './http'

export type AuthTokens = {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
}

export type LoginPayload = {
  account: string
  password: string
  captcha_id?: string
  captcha_code?: string
}

export type CaptchaChallengeResponse = {
  captcha_id: string
  image_base64: string
  expires_in: number
}

export type UserProfile = {
  id: string
  username: string
  email: string
  is_active: boolean
}

export const authApi = {
  register: (payload: { username: string; email: string; password: string }) =>
    requestJson<UserProfile>('/api/auth/register', { method: 'POST', body: payload }),

  login: (payload: LoginPayload) =>
    requestJson<AuthTokens>('/api/auth/login', { method: 'POST', body: payload }),

  getCaptchaChallenge: () =>
    requestJson<CaptchaChallengeResponse>('/api/auth/captcha', { method: 'GET' }),

  refresh: (refreshToken: string) =>
    requestJson<AuthTokens>('/api/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }),

  me: (accessToken: string) =>
    requestJson<UserProfile>('/api/auth/me', { method: 'GET', accessToken }),

  changePassword: (
    accessToken: string,
    payload: { current_password: string; new_password: string },
  ) =>
    requestJson<{ message: string }>('/api/auth/change-password', {
      method: 'POST',
      body: payload,
      accessToken,
    }),

  logout: (refreshToken: string) =>
    requestJson<{ message: string }>('/api/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }),
}
