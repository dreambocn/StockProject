import { createI18n } from 'vue-i18n'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

export const LOCALE_STORAGE_KEY = 'app.locale'
export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

const resolveInitialLocale = (): AppLocale => {
  if (typeof window === 'undefined') return 'zh-CN'

  // 仅接受白名单语言，防止本地缓存脏值导致 i18n 初始化异常。
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
  // 语言切换统一入口：同步更新运行时语言与本地持久化。
  i18n.global.locale.value = locale
  if (typeof window !== 'undefined') {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  }
}
