import { defineStore } from "pinia"

const TTL_MS = 5000
let counter = 0

export const useToastStore = defineStore("toasts", {
  state: () => ({ toasts: [] }),
  actions: {
    push(level, title, body = "") {
      const id = (counter += 1)
      this.toasts.push({ id, level, title, body })
      setTimeout(() => this.dismiss(id), TTL_MS)
      return id
    },
    info(title, body) {
      return this.push("info", title, body)
    },
    ok(title, body) {
      return this.push("ok", title, body)
    },
    warn(title, body) {
      return this.push("warn", title, body)
    },
    error(title, body) {
      return this.push("error", title, body)
    },
    dismiss(id) {
      this.toasts = this.toasts.filter((t) => t.id !== id)
    },
  },
})
