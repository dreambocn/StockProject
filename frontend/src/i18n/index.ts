import { createI18n } from 'vue-i18n'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

export const LOCALE_STORAGE_KEY = 'app.locale'
export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

const resolveInitialLocale = (): AppLocale => {
  if (typeof window === 'undefined') return 'zh-CN'

  const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
  if (stored && SUPPORTED_LOCALES.includes(stored as AppLocale)) {
    return stored as AppLocale
  }

  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  locale: resolveInitialLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export const setAppLocale = (locale: AppLocale) => {
  i18n.global.locale.value = locale
  if (typeof window !== 'undefined') {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  }
}
