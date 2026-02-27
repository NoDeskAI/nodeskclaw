import { createI18n } from 'vue-i18n'
import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

export type AppLocale = 'zh-CN' | 'en-US'

const LOCALE_STORAGE_KEY = 'portal_locale'
const FALLBACK_LOCALE: AppLocale = 'en-US'
const SUPPORTED_LOCALES: AppLocale[] = ['zh-CN', 'en-US']

function normalizeLocale(input: string | null | undefined): AppLocale {
  if (!input) return FALLBACK_LOCALE
  const lower = input.toLowerCase()
  if (lower.startsWith('zh')) return 'zh-CN'
  if (lower.startsWith('en')) return 'en-US'
  return FALLBACK_LOCALE
}

function detectInitialLocale(): AppLocale {
  if (typeof window === 'undefined') return FALLBACK_LOCALE
  const fromStorage = window.localStorage.getItem(LOCALE_STORAGE_KEY)
  if (fromStorage && SUPPORTED_LOCALES.includes(fromStorage as AppLocale)) {
    return fromStorage as AppLocale
  }
  if (Array.isArray(window.navigator.languages) && window.navigator.languages.length > 0) {
    return normalizeLocale(window.navigator.languages[0])
  }
  return normalizeLocale(window.navigator.language)
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectInitialLocale(),
  fallbackLocale: FALLBACK_LOCALE,
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export function getCurrentLocale(): AppLocale {
  return normalizeLocale(String(i18n.global.locale.value))
}

export function setCurrentLocale(locale: string): AppLocale {
  const resolved = normalizeLocale(locale)
  i18n.global.locale.value = resolved
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, resolved)
    document.documentElement.lang = resolved
  }
  return resolved
}

if (typeof window !== 'undefined') {
  document.documentElement.lang = getCurrentLocale()
}
