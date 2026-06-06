/**
 * F2: vue-i18n 脚手架。
 * 当前两个语言：zh-CN（默认）与 en-US。语言切换在 SettingsView 的"通用" tab。
 * 渐进式 i18n：组件可以暂时不调 t()，等需要双语时再替换字面量。
 */
import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

const SUPPORTED = ['zh-CN', 'en-US'] as const
export type Locale = typeof SUPPORTED[number]

function detectLocale(): Locale {
  const saved = localStorage.getItem('lumi-locale')
  if (saved && (SUPPORTED as readonly string[]).includes(saved)) return saved as Locale
  const nav = (navigator.language || 'zh-CN').toLowerCase()
  if (nav.startsWith('en')) return 'en-US'
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale:        detectLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export function setLocale(loc: Locale) {
  i18n.global.locale.value = loc
  localStorage.setItem('lumi-locale', loc)
}

export const availableLocales: { value: Locale; label: string }[] = [
  { value: 'zh-CN', label: '中文（简体）' },
  { value: 'en-US', label: 'English' },
]
