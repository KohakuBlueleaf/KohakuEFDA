<script setup>
import { STAGES, useAppStore } from "@/stores/app"

const store = useAppStore()

const ready = computed(() => {
  const out = {}
  STAGES.forEach((stage, position) => {
    out[stage] =
      Boolean(store.run) && STAGES.slice(0, position).every((s) => store.stageStatus(s) === "done")
  })
  return out
})

function run(stage) {
  store.pinnedStage = false
  store.startStage(stage, currentParams(stage))
}

function runThrough(stage) {
  store.pinnedStage = false
  store.startStage(stage, currentParams(stage), "verify")
}

function currentParams(stage) {
  return { ...store.draftParams(stage) }
}
</script>

<template>
  <div class="flex items-stretch gap-1 overflow-x-auto pb-1">
    <template v-for="(stage, position) in STAGES" :key="stage">
      <StageCard
        :stage="stage"
        :position="position"
        :state="store.run?.stages?.[stage] ?? null"
        :ready="ready[stage]"
        :busy="store.runBusy"
        :selected="store.selectedStage === stage"
        :last="position === STAGES.length - 1"
        @run="run"
        @run-through="runThrough"
        @cancel="store.cancelRun()"
        @select="store.selectStage(stage)"
      />
      <span
        v-if="position < STAGES.length - 1"
        class="i-carbon-arrow-right self-center text-warm-300 dark:text-warm-600 shrink-0"
      />
    </template>
  </div>
</template>
