import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ja from './locales/ja.json'
import mesEn from './locales/mes/en.json'
import mesJa from './locales/mes/ja.json'
import mesZh from './locales/mes/zh-CN.json'
import zhCN from './locales/zh-CN.json'

type Tree = { [k: string]: string | Tree }
/** app strings + generated MES bundles (mes.*, menu.mes-*) */
function deepMerge(a: Tree, b: Tree): Tree {
  const out: Tree = { ...a }
  for (const [k, v] of Object.entries(b)) {
    const cur = out[k]
    out[k] =
      typeof v === 'object' && typeof cur === 'object' ? deepMerge(cur, v) : v
  }
  return out
}

export const LANGUAGES = ['zh-CN', 'ja', 'en'] as const
export type Language = (typeof LANGUAGES)[number]
export const DEFAULT_LANGUAGE: Language = 'zh-CN'
export const LANGUAGE_STORAGE_KEY = 'lang'

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'zh-CN': { translation: deepMerge(zhCN, mesZh) },
      ja: { translation: deepMerge(ja, mesJa) },
      en: { translation: deepMerge(en, mesEn) },
    },
    supportedLngs: [...LANGUAGES],
    nonExplicitSupportedLngs: false,
    load: 'currentOnly',
    fallbackLng: DEFAULT_LANGUAGE, // default is zh-CN, never the browser language
    detection: {
      order: ['localStorage'], // only an explicit, persisted choice
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ['localStorage'],
    },
    interpolation: { escapeValue: false },
    nsSeparator: false, // permission codes and backend messages contain ':'
    returnNull: false,
  })

const syncHtmlLang = (lng: string) => {
  document.documentElement.lang = lng
}
syncHtmlLang(i18n.resolvedLanguage ?? DEFAULT_LANGUAGE)
i18n.on('languageChanged', syncHtmlLang)

/** Current language (always one of LANGUAGES). */
export const currentLanguage = (): Language =>
  (LANGUAGES as readonly string[]).includes(i18n.resolvedLanguage ?? '')
    ? (i18n.resolvedLanguage as Language)
    : DEFAULT_LANGUAGE

/** Translate outside React components (toasts, schemas, helpers). */
export const t = i18n.t.bind(i18n)

export const fmtDate = (v: string | number | Date | null | undefined) =>
  v
    ? new Intl.DateTimeFormat(currentLanguage(), {
        dateStyle: 'medium',
      }).format(new Date(v))
    : ''
export const fmtDateTime = (v: string | number | Date | null | undefined) =>
  v
    ? new Intl.DateTimeFormat(currentLanguage(), {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(v))
    : ''
export const fmtNumber = (v: number | null | undefined) =>
  v == null ? '—' : new Intl.NumberFormat(currentLanguage()).format(v)

export default i18n
