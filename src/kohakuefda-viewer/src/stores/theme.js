import { defineStore } from "pinia"

const THEME_KEY = "kohakuefda.theme"

function stored() {
  try {
    return localStorage.getItem(THEME_KEY) || "system"
  } catch {
    return "system"
  }
}

function systemDark() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
}

export const useThemeStore = defineStore("theme", {
  state: () => ({ dark: false, choice: "system" }),
  actions: {
    init() {
      this.choice = stored()
      this.dark = this.choice === "dark" || (this.choice === "system" && systemDark())
      this.apply()
    },
    toggle() {
      this.dark = !this.dark
      this.choice = this.dark ? "dark" : "light"
      try {
        localStorage.setItem(THEME_KEY, this.choice)
      } catch {
        return
      }
      this.apply()
    },
    apply() {
      document.documentElement.classList.toggle("dark", this.dark)
    },
  },
})
