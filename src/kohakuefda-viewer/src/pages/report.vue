<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()

const counts = computed(() => {
  const findings = store.report?.findings ?? []
  const count = (severity) => findings.filter((f) => f.severity === severity).length
  return { errors: count("error"), warnings: count("warning"), infos: count("info") }
})
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-5xl mx-auto px-4 py-4 flex flex-col gap-3">
      <h1 class="text-lg font-semibold">{{ t("report.heading") }}</h1>
      <p v-if="!store.report" class="card p-8 text-center text-secondary">
        {{ t("status.missing") }}
      </p>
      <template v-else>
        <div class="flex items-center gap-2 flex-wrap text-xs">
          <span class="text-secondary">{{ store.report.subject }}</span>
          <span :class="counts.errors ? 'chip-coral' : 'chip-aqua'">{{
            t("verify.errors", { n: counts.errors })
          }}</span>
          <span class="chip-amber">{{ t("verify.warnings", { n: counts.warnings }) }}</span>
          <span class="chip-sapphire">{{ t("verify.notes", { n: counts.infos }) }}</span>
        </div>
        <FindingsTable :findings="store.report.findings" />
      </template>
    </div>
  </div>
</template>
