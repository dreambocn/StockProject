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
  user_level: 'user' | 'admin'
}

export type EmailCodeSendResponse = {
  message: string
  expires_in: number
  cooldown_in: number
}

export const authApi = {
  // 认证相关接口统一在此收口，避免页面层散落路径与 payload 结构。
  sendRegisterEmailCode: (email: string) =>
    requestJson<EmailCodeSendResponse>('/api/auth/register/email-code', {
      method: 'POST',
      body: { email },
    }),

  register: (payload: { username: string; email: string; email_code: string; password: string }) =>
    requestJson<UserProfile>('/api/auth/register', { method: 'POST', body: payload }),

  login: (payload: LoginPayload) =>
    requestJson<AuthTokens>('/api/auth/login', { method: 'POST', body: payload }),

  getCaptchaChallenge: () =>
    requestJson<CaptchaChallengeResponse>('/api/auth/captcha', { method: 'GET' }),

  refresh: (refreshToken: string) =>
    // 刷新接口只接受 refresh token，access token 过期由后端统一校验。
    requestJson<AuthTokens>('/api/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }),

  me: (accessToken: string) =>
    requestJson<UserProfile>('/api/auth/me', { method: 'GET', accessToken }),

  changePassword: (
    accessToken: string,
    payload: { current_password: string; new_password: string; email_code: string },
  ) =>
    requestJson<{ message: string }>('/api/auth/change-password', {
      method: 'POST',
      body: payload,
      accessToken,
    }),

  sendChangePasswordEmailCode: (accessToken: string) =>
    requestJson<EmailCodeSendResponse>('/api/auth/change-password/email-code', {
      method: 'POST',
      accessToken,
    }),

  sendResetPasswordEmailCode: (email: string) =>
    requestJson<EmailCodeSendResponse>('/api/auth/reset-password/email-code', {
      method: 'POST',
      body: { email },
    }),

  resetPassword: (payload: { email: string; email_code: string; new_password: string }) =>
    requestJson<{ message: string }>('/api/auth/reset-password', {
      method: 'POST',
      body: payload,
    }),

  logout: (refreshToken: string) =>
    // 登出通过撤销 refresh token 实现，access token 自然到期。
    requestJson<{ message: string }>('/api/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }),
}
