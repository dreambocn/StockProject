import { describe, expect, it } from 'vitest'

import { ApiError } from '../api/http'
import { mapApiErrorMessage } from './apiErrorI18n'

const messages: Record<string, string> = {
  'errors.invalidCredentials': '用户名或密码错误',
  'errors.usernameOrEmailExists': '用户名或邮箱已存在',
  'errors.passwordPolicy': '密码强度不符合要求',
  'errors.emailCodeInvalid': '邮箱验证码错误或已过期',
  'errors.emailCodeTooFrequent': '验证码发送过于频繁，请稍后重试',
  'errors.emailServiceUnavailable': '邮件服务暂不可用，请稍后重试',
  'errors.authServiceUnavailable': '认证服务暂不可用，请稍后重试',
  'errors.validation.required': '{field}为必填项',
  'errors.validation.tooShort': '{field}至少 {min} 位',
  'errors.validation.tooLong': '{field}最多 {max} 位',
  'errors.validation.invalidEmail': '邮箱格式不正确',
  'errors.validation.unknown': '{field}输入不合法',
  'errors.fields.email': '邮箱',
  'errors.fields.username': '用户名',
  'errors.fallback': '请求失败',
}

const t = (key: string, params?: Record<string, unknown>) => {
  const template = messages[key] ?? key
  if (!params) return template

  return template.replace(/\{(\w+)\}/g, (_, token: string) => String(params[token] ?? ''))
}

describe('mapApiErrorMessage', () => {
  it('maps known backend message to localized text', () => {
    const error = new ApiError('invalid credentials', 401, {
      detail: 'invalid credentials',
    })

    expect(mapApiErrorMessage(error, t, 'errors.fallback')).toBe('用户名或密码错误')
  })

  it('maps email verification error messages', () => {
    const invalidCodeError = new ApiError('email verification code invalid', 400, {
      detail: 'email verification code invalid',
    })
    const tooFrequentError = new ApiError('email verification code send too frequent', 429, {
      detail: 'email verification code send too frequent',
    })
    const serviceUnavailableError = new ApiError('email service unavailable', 503, {
      detail: 'email service unavailable',
    })
    const authServiceUnavailableError = new ApiError('auth service unavailable', 503, {
      detail: 'auth service unavailable',
    })

    expect(mapApiErrorMessage(invalidCodeError, t, 'errors.fallback')).toBe('邮箱验证码错误或已过期')
    expect(mapApiErrorMessage(tooFrequentError, t, 'errors.fallback')).toBe('验证码发送过于频繁，请稍后重试')
    expect(mapApiErrorMessage(serviceUnavailableError, t, 'errors.fallback')).toBe('邮件服务暂不可用，请稍后重试')
    expect(mapApiErrorMessage(authServiceUnavailableError, t, 'errors.fallback')).toBe('认证服务暂不可用，请稍后重试')
  })

  it('uses detail.message when backend returns detail object', () => {
    const error = new ApiError('captcha required', 401, {
      detail: { message: 'invalid credentials', captcha_required: true },
    })

    expect(mapApiErrorMessage(error, t, 'errors.fallback')).toBe('用户名或密码错误')
  })

  it('keeps already-localized message without remapping', () => {
    const error = new ApiError('两次输入的密码不一致', 400)

    expect(mapApiErrorMessage(error, t, 'errors.fallback')).toBe('两次输入的密码不一致')
  })

  it('maps pydantic missing field validation error', () => {
    const error = new ApiError('Request failed', 422, {
      detail: [
        {
          type: 'missing',
          loc: ['body', 'email'],
          msg: 'Field required',
        },
      ],
    })

    expect(mapApiErrorMessage(error, t, 'errors.fallback')).toBe('邮箱为必填项')
  })

  it('maps pydantic min length validation error', () => {
    const error = new ApiError('Request failed', 422, {
      detail: [
        {
          type: 'string_too_short',
          loc: ['body', 'username'],
          msg: 'String should have at least 3 characters',
          ctx: { min_length: 3 },
        },
      ],
    })

    expect(mapApiErrorMessage(error, t, 'errors.fallback')).toBe('用户名至少 3 位')
  })

  it('maps email invalid validation error', () => {
    const error = new ApiError('Request failed', 422, {
      detail: [
        {
          type: 'value_error',
          loc: ['body', 'email'],
          msg: 'value is not a valid email address',
        },
      ],
    })

    expect(mapApiErrorMessage(error, t, 'errors.fallback')).toBe('邮箱格式不正确')
  })
})
