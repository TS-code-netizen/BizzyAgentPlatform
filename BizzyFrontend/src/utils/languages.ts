export interface LanguageOption {
  code: string
  label: string
}

export const LANGUAGES: readonly LanguageOption[] = [
  { code: 'en', label: 'English' },
  { code: 'ta', label: 'Tamil' },
  { code: 'zh-CN', label: 'Mandarin' },
  { code: 'ms', label: 'Bahasa Melayu' },
  { code: 'hi', label: 'Hindi' },
]

export const DEFAULT_LANGUAGE = LANGUAGES[0].code

export function languageLabel(code: string): string {
  return LANGUAGES.find((language) => language.code === code)?.label ?? code
}

// The backend only localises summaries for English and Chinese (zh*) locales; others fall back to English.
export function hasLocalisedSummaries(code: string): boolean {
  return code === 'en' || code.toLowerCase().startsWith('zh')
}
