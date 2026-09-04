<script setup>
import { useI18n } from "@/i18n"
import { STAGES, useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const now = ref(Date.now())
let timer = 0

onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onUnmounted(() => clearInterval(timer))

const stageLine = computed(() => {
  if (!store.run) {
    return t("status.noRun")
  }
  const active = store.activeStage
  if (active) {
    const state = store.run.stages[active]
    const seconds = state.started ? Math.max(0, (now.value / 1000 - state.started) | 0) : 0
    return `${t(`stage.${active}`)} ${t("flow.status.running")} ${seconds}s`
  }
  const done = STAGES.filter((s) => store.stageStatus(s) === "done").length
  return t("status.stagesDone", { n: done, total: STAGES.length })
})
</script>

<template>
  <footer
    class="flex items-center gap-2 px-3 h-6 text-[10px] font-mono bg-warm-100 dark:bg-warm-950 border-t border-warm-200 dark:border-warm-700 text-warm-500 shrink-0 overflow-hidden"
  >
    <span>{{ store.dataset?.version?.id ?? "—" }}</span>
    <span class="sep" />
    <span v-if="store.run">{{ t("status.run") }} {{ store.run.id }}</span>
    <span v-else>{{ t("status.source") }} {{ store.source || "—" }}</span>
    <span class="sep" />
    <span :class="store.runBusy ? 'text-aquamarine' : ''">{{ stageLine }}</span>
    <span class="flex-1" />
    <span v-if="store.run">{{ t("status.frames") }} {{ store.frames.layout?.length ?? 0 }}</span>
    <span class="sep" />
    <span :class="store.apiAvailable ? 'text-aquamarine' : 'text-coral'">
      {{ store.apiAvailable ? t("status.apiOn") : t("status.apiOff") }}
    </span>
  </footer>
</template>

<style scoped>
.sep {
  width: 1px;
  height: 12px;
  background: currentColor;
  opacity: 0.15;
  flex-shrink: 0;
}
</style>
