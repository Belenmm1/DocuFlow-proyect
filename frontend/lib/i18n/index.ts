'use client'

import { t as es } from './es'
import { t as en } from './en'

export type Locale = 'es' | 'en'

const STORAGE_KEY = 'docuflow_locale'

export function getLocale(): Locale {
  if (typeof window === 'undefined') return 'es'
  return (localStorage.getItem(STORAGE_KEY) as Locale) ?? 'es'
}

export function setLocale(locale: Locale) {
  if (typeof window === 'undefined') return
  localStorage.setItem(STORAGE_KEY, locale)
  window.dispatchEvent(new Event('locale-change'))
}

export function useTranslations() {
  if (typeof window === 'undefined') return es
  return getLocale() === 'en' ? en : es
}

export { es, en }
