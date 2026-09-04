import { computed } from "vue"
import { useAppStore } from "@/stores/app"

export function pickName(names, lang) {
  if (!names) {
    return ""
  }
  if (lang === "zh-TW") {
    return names.zh_tw || names.zh_cn || names.en || ""
  }
  if (lang === "zh-CN") {
    return names.zh_cn || names.zh_tw || names.en || ""
  }
  return names.en || ""
}

export function toNumber(rate) {
  if (typeof rate === "number") {
    return rate
  }
  const text = String(rate ?? "0")
  const [num, den] = text.split("/")
  const value = Number(num) / (den ? Number(den) : 1)
  return Number.isFinite(value) ? value : 0
}

export function formatRate(rate) {
  const value = toNumber(rate)
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

export function useNames() {
  const store = useAppStore()
  const lang = computed(() => store.lang)
  function of(table, id) {
    const entry = store.dataset?.[table]?.[id]
    return entry ? pickName(entry.names, lang.value) : id
  }
  return {
    lang,
    item: (id) => of("items", id),
    machine: (id) => of("machines", id),
    recipe: (id) => of("recipes", id),
    unit: (id) => of("logistics", id),
  }
}
