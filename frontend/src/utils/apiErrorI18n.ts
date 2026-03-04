import { ApiError } from '../api/http'

type Translate = (key: string, params?: Record<string, unknown>) => string

const API_ERROR_KEY_MAP: Record<string, string> = {
  'invalid credentials': 'errors.invalidCredentials',
  'inactive user': 'errors.inactiveUser',
  'username or email already exists': 'errors.usernameOrEmailExists',
  'current password is incorrect': 'errors.currentPasswordIncorrect',
  'captcha required': 'errors.captchaRequired',
  'captcha invalid': 'errors.captchaInvalid',
  'email verification code invalid': 'errors.emailCodeInvalid',
  'email verification code send too frequent': 'errors.emailCodeTooFrequent',
  'email service unavailable': 'errors.emailServiceUnavailable',
  'Password must be 8-128 chars and include uppercase, lowercase, number, and special character':
    'errors.passwordPolicy',
}

const hasCjk = (value: string) => /[\u4e00-\u9fff]/.test(value)

type ValidationDetailItem = {
  type?: unknown
  msg?: unknown
  loc?: unknown
  ctx?: unknown
}

const FIELD_KEY_MAP: Record<string, string> = {
  account: 'errors.fields.account',
  password: 'errors.fields.password',
  username: 'errors.fields.username',
  email: 'errors.fields.email',
  confirmPassword: 'errors.fields.confirmPassword',
  current_password: 'errors.fields.currentPassword',
  new_password: 'errors.fields.newPassword',
  captcha_code: 'errors.fields.captchaCode',
}

const resolveValidationFieldName = (
  detail: ValidationDetailItem,
  t: Translate,
) => {
  const location = Array.isArray(detail.loc) ? detail.loc : []
  const fieldKey = String(location[location.length - 1] ?? '')
  const mappedFieldKey = FIELD_KEY_MAP[fieldKey]
  if (mappedFieldKey) return t(mappedFieldKey)
  return fieldKey || t('errors.fields.generic')
}

const getCtxValue = (ctx: unknown, key: string): number | undefined => {
  if (!ctx || typeof ctx !== 'object' || !(key in ctx)) return undefined
  const value = (ctx as Record<string, unknown>)[key]
  return typeof value === 'number' ? value : undefined
}

const mapValidationDetailItem = (
  detail: ValidationDetailItem,
  t: Translate,
): string | null => {
  const type = typeof detail.type === 'string' ? detail.type : ''
  const message = typeof detail.msg === 'string' ? detail.msg : ''
  const field = resolveValidationFieldName(detail, t)

  if (type === 'missing') {
    return t('errors.validation.required', { field })
  }

  if (type === 'string_too_short') {
    const min = getCtxValue(detail.ctx, 'min_length') ?? 1
    return t('errors.validation.tooShort', { field, min })
  }

  if (type === 'string_too_long') {
    const max = getCtxValue(detail.ctx, 'max_length') ?? 255
    return t('errors.validation.tooLong', { field, max })
  }

  if (type === 'value_error' && String(field) === t('errors.fields.email')) {
    return t('errors.validation.invalidEmail')
  }

  if (API_ERROR_KEY_MAP[message]) {
    return t(API_ERROR_KEY_MAP[message])
  }

  if (message && hasCjk(message)) {
    return message
  }

  return t('errors.validation.unknown', { field })
}

const resolveValidationArrayMessage = (
  detail: unknown,
  t: Translate,
): string | null => {
  if (!Array.isArray(detail) || detail.length === 0) return null

  const firstItem = detail[0]
  if (!firstItem || typeof firstItem !== 'object') return null

  return mapValidationDetailItem(firstItem as ValidationDetailItem, t)
}

const resolveErrorMessage = (error: ApiError): string | null => {
  if (!error.payload || typeof error.payload !== 'object' || !('detail' in error.payload)) {
    return error.message || null
  }

  const detail = (error.payload as { detail: unknown }).detail
  if (typeof detail === 'string') return detail

  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string') return message
  }

  return error.message || null
}

export const mapApiErrorMessage = (
  error: unknown,
  t: Translate,
  fallbackKey: string,
): string => {
  if (!(error instanceof ApiError)) {
    if (error instanceof Error && error.message) return error.message
    return t(fallbackKey)
  }

  if (error.status === 422 && error.payload && typeof error.payload === 'object' && 'detail' in error.payload) {
    const validationMessage = resolveValidationArrayMessage(
      (error.payload as { detail: unknown }).detail,
      t,
    )
    if (validationMessage) return validationMessage
  }

  const rawMessage = resolveErrorMessage(error)
  if (!rawMessage) return t(fallbackKey)
  if (hasCjk(rawMessage)) return rawMessage

  const mappedKey = API_ERROR_KEY_MAP[rawMessage]
  if (mappedKey) return t(mappedKey)

  return rawMessage
}
