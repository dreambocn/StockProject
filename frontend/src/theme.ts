import { ref } from 'vue'

export const APP_THEME_STORAGE_KEY = 'app.theme'
export const SUPPORTED_THEMES = ['light', 'dark'] as const
export type AppTheme = (typeof SUPPORTED_THEMES)[number]

export const themeState = ref<AppTheme>('light')

const normalizeTheme = (value: string | null | undefined): AppTheme => {
  if (value && SUPPORTED_THEMES.includes(value as AppTheme)) {
    return value as AppTheme
  }
  return 'light'
}

export const resolveInitialTheme = (): AppTheme => {
  if (typeof window === 'undefined') {
    return 'light'
  }

  // 主题默认值固定为白天，避免首次打开时仍落回深色影响截图。
  return normalizeTheme(window.localStorage.getItem(APP_THEME_STORAGE_KEY))
}

export const applyDocumentTheme = (theme: AppTheme) => {
  if (typeof document === 'undefined') {
    return
  }

  // 统一把主题状态挂到根节点，便于全局 token 和组件 scoped 样式一起读取。
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
}

export const initializeAppTheme = () => {
  const theme = resolveInitialTheme()
  themeState.value = theme
  applyDocumentTheme(theme)

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(APP_THEME_STORAGE_KEY, theme)
  }
}

export const setAppTheme = (theme: AppTheme) => {
  const normalizedTheme = normalizeTheme(theme)
  themeState.value = normalizedTheme
  applyDocumentTheme(normalizedTheme)

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(APP_THEME_STORAGE_KEY, normalizedTheme)
  }
}
