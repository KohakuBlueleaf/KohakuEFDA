<script setup>
import { useToastStore } from "@/stores/toasts"

const toasts = useToastStore()
const BORDER = {
  info: "border-iolite/40",
  ok: "border-aquamarine/40",
  warn: "border-amber/40",
  error: "border-coral/40",
}
const ICON = {
  info: "i-carbon-information text-iolite",
  ok: "i-carbon-checkmark text-aquamarine",
  warn: "i-carbon-warning-alt text-amber",
  error: "i-carbon-error text-coral",
}
</script>

<template>
  <div class="fixed bottom-8 right-4 flex flex-col gap-2 z-50 pointer-events-none">
    <TransitionGroup name="fade">
      <div
        v-for="toast in toasts.toasts.slice(-5)"
        :key="toast.id"
        class="min-w-56 max-w-96 rounded-lg border px-3 py-2 text-xs shadow-lg bg-white/95 dark:bg-warm-900/95 pointer-events-auto flex items-start gap-2"
        :class="BORDER[toast.level]"
      >
        <span :class="ICON[toast.level]" class="text-base shrink-0 mt-0.5" />
        <div class="flex-1 min-w-0">
          <div class="font-medium text-warm-700 dark:text-warm-300 truncate">{{ toast.title }}</div>
          <div v-if="toast.body" class="text-warm-600 dark:text-warm-400 break-words">
            {{ toast.body }}
          </div>
        </div>
        <button class="text-warm-400 hover:text-warm-600" @click="toasts.dismiss(toast.id)">
          <span class="i-carbon-close text-[11px]" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
