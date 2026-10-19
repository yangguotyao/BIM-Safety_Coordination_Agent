import { reactive } from 'vue'
import zh from './zh'
import en from './en'
import uiEn from './ui-en'

export type Locale = 'zh' | 'en'

const STORAGE_KEY = 'bim-locale'
// uiEn 是界面文案的中文原文对照表，en 是语义 key 表；两者 key 不重叠。
const DICTS: Record<Locale, Record<string, string>> = { zh, en: { ...uiEn, ...en } }

function readStored(): Locale {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'en' ? 'en' : 'zh'
  } catch {
    return 'zh'
  }
}

export const localeState = reactive<{ locale: Locale }>({ locale: readStored() })

const listeners = new Set<(locale: Locale) => void>()

export function onLocaleChange(callback: (locale: Locale) => void): () => void {
  listeners.add(callback)
  return () => listeners.delete(callback)
}

export function setLocale(next: Locale): void {
  if (next === localeState.locale) return
  localeState.locale = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* 存储不可用时仅保留会话内状态 */
  }
  document.documentElement.lang = next === 'en' ? 'en' : 'zh-CN'
  listeners.forEach((callback) => callback(next))
}

export function applyDocumentLang(): void {
  document.documentElement.lang = localeState.locale === 'en' ? 'en' : 'zh-CN'
}

export function currentLocale(): Locale {
  return localeState.locale
}

/** 按当前语言取词条；缺失时回退中文，再回退 key 本身。 */
export function t(key: string, params?: Record<string, string | number>): string {
  const dict = DICTS[localeState.locale]
  let text = dict[key] ?? zh[key] ?? key
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.split(`{${name}}`).join(String(value))
    }
  }
  return text
}

/** 根据当前语言调整本地化格式，日期与数字复用。 */
export function localeTag(): string {
  return localeState.locale === 'en' ? 'en-US' : 'zh-CN'
}
