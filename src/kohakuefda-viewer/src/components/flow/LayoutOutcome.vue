<script setup>
import { useI18n } from "@/i18n"
import { layoutOutcome } from "@/layout-settings"
import { useAppStore } from "@/stores/app"

const store = useAppStore()
const { t } = useI18n()
const result = computed(() => layoutOutcome(store.run?.stages?.layout, store.frames.layout))
const runtime = computed(() => result.value?.settings?.runtime ?? {})
const options = computed(() => result.value?.settings?.solver_settings ?? {})
const reason = computed(() => {
  const key = `solverUI.reason.${result.value?.status}`
  const value = t(key)
  return value === key ? result.value?.status : value
})
</script>

<template>
  <div
    v-if="result"
    class="card p-2 flex flex-col gap-1 text-xs"
    :class="result.routed ? '' : 'border-amber'"
    role="status"
  >
    <strong>{{ t(result.routed ? "solverUI.routedResult" : "solverUI.incompleteResult") }}</strong>
    <span>{{ reason }}</span>
    <span v-if="result.total !== undefined" class="font-mono"
      >{{ result.placed }} / {{ result.total }} ·
      {{ Number(result.elapsed || 0).toFixed(2) }} s</span
    >
    <span class="text-secondary"
      >{{ t("solverUI.usedLimits") }}: {{ runtime.seconds ?? 0 }} s · {{ runtime.max_actions ?? 0 }}
      {{ t("solverUI.actions") }}</span
    >
    <span v-if="options.construction_steps !== undefined" class="text-secondary"
      >{{ t("params.construction_steps") }}: {{ options.construction_steps }} ·
      {{ t("params.until_budget") }}: {{ String(options.until_budget) }}</span
    >
    <span v-if="result.work" class="text-secondary"
      >{{ t("solverUI.workUsed") }}: {{ result.work.actions ?? 0 }} {{ t("solverUI.actions") }} ·
      {{ result.work.route_calls ?? 0 }} {{ t("solverUI.routes") }}</span
    >
    <span v-if="!result.routed" class="text-amber">{{ t("solverUI.incompleteHint") }}</span>
    <span v-else-if="result.status === 'budget_exhausted'" class="text-secondary">{{
      t("solverUI.bestRetained")
    }}</span>
  </div>
</template>
