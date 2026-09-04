import { computed } from "vue"
import { useAppStore } from "@/stores/app"
import en from "./en.json"
import zhTW from "./zh-TW.json"
import zhCN from "./zh-CN.json"

const MESSAGES = { en, "zh-TW": zhTW, "zh-CN": zhCN }
export const LANGUAGES = Object.keys(MESSAGES)

function lookup(table, key) {
  return key.split(".").reduce((node, part) => (node == null ? node : node[part]), table)
}

function interpolate(text, params) {
  return text.replace(/\{(\w+)\}/g, (match, name) =>
    name in params ? String(params[name]) : match,
  )
}

export function useI18n() {
  const store = useAppStore()
  const lang = computed(() => store.lang)
  function t(key, params = {}) {
    const text = lookup(MESSAGES[store.lang], key) ?? lookup(MESSAGES.en, key) ?? key
    return interpolate(text, params)
  }
  return { t, lang, languages: LANGUAGES, setLang: store.setLang }
}
