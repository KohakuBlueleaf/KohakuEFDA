<script setup>
import { useI18n } from "@/i18n"
import { collectLayout } from "@/layout-settings"
import { STAGES, useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const stage = computed(() => store.selectedStage)
const state = computed(() => store.run?.stages?.[stage.value] ?? null)
const defaults = computed(() => store.params[stage.value] ?? {})
const params = computed(() => store.draftParams(stage.value))
const status = computed(() => store.stageStatus(stage.value))
const active = computed(() => ["running", "queued"].includes(status.value))
const ready = computed(() => {
  const position = STAGES.indexOf(stage.value)
  return (
    Boolean(store.run) && STAGES.slice(0, position).every((s) => store.stageStatus(s) === "done")
  )
})
const lines = computed(() => store.log.filter((entry) => entry.stage === stage.value).reverse())
const checked = computed(() => {
  try {
    return {
      payload:
        stage.value === "layout"
          ? collectLayout(defaults.value, store.solvers, params.value)
          : { ...params.value },
      error: "",
    }
  } catch (error) {
    return { payload: null, error: String(error.message) }
  }
})
const progress = computed(() => {
  const frames = store.frames[stage.value] ?? []
  const last = frames.at(-1)
  if (!active.value || !last) return null
  if (last.kind === "build")
    return { phase: "spread", done: last.placed ?? 0, total: last.total ?? 0 }
  if (last.kind === "improve")
    return { phase: "improve", done: last.step ?? 0, total: last.of ?? 0 }
  return null
})
function when(entry) {
  const time = entry.finished ?? entry.started ?? entry.time
  return new Date(time * 1000).toLocaleTimeString()
}
function start(through = null) {
  if (checked.value.payload) store.startStage(stage.value, checked.value.payload, through)
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="panel-header">
      <span class="font-medium text-warm-700 dark:text-warm-300">{{ t(`stage.${stage}`) }}</span>
      <span class="flex-1" />
      <StatusDot :status="status" />
      <span>{{ t(`flow.status.${status}`) }}</span>
    </div>
    <div class="flex-1 overflow-y-auto p-3 flex flex-col gap-3 text-xs">
      <p class="text-secondary">{{ t(`stageHelp.${stage}`) }}</p>
      <LayoutSettings v-if="stage === 'layout'" />
      <template v-else-if="Object.keys(defaults).length">
        <SettingField
          v-for="(value, key) in defaults"
          :key="key"
          :field="{
            key,
            type: typeof value === 'boolean' ? 'bool' : typeof value === 'string' ? 'str' : 'float',
          }"
          :value="params[key]"
          @change="params[key] = $event"
        />
      </template>
      <div v-if="progress" class="flex flex-col gap-1 rounded bg-warm-100 dark:bg-warm-800 p-2">
        <div class="flex items-center gap-2">
          <span class="font-medium">{{ t(`phase.${progress.phase}`) }}</span>
          <span class="flex-1" />
          <span class="text-secondary tabular-nums"
            >{{ progress.done
            }}<template v-if="progress.total"> / {{ progress.total }}</template></span
          >
        </div>
        <div class="h-1 rounded bg-warm-300 dark:bg-warm-700 overflow-hidden">
          <div
            class="h-full bg-sky transition-all"
            :style="{
              width: progress.total
                ? `${Math.min(100, (100 * progress.done) / progress.total)}%`
                : '100%',
            }"
          />
        </div>
      </div>
      <LayoutOutcome v-if="stage === 'layout'" />
      <LayoutCost v-if="stage === 'layout'" />
      <div class="flex gap-1.5 flex-wrap">
        <button v-if="active" class="btn-secondary !text-xs text-coral" @click="store.cancelRun()">
          <span class="i-carbon-stop-filled-alt" /> {{ t("flow.cancel") }}
        </button>
        <template v-else>
          <button
            class="btn-primary !text-xs"
            :disabled="!ready || store.runBusy || !!checked.error"
            @click="start()"
          >
            <span class="i-carbon-play-filled-alt" /> {{ t("flow.run") }}
          </button>
          <button
            v-if="stage !== 'verify'"
            class="btn-secondary !text-xs"
            :disabled="!ready || store.runBusy || !!checked.error"
            @click="start('verify')"
          >
            <span class="i-carbon-skip-forward-filled" /> {{ t("flow.runThrough") }}
          </button>
        </template>
      </div>
      <p v-if="!store.run" class="text-secondary">{{ t("flow.noRun") }}</p>
      <p v-else-if="!ready" class="text-secondary">{{ t("flow.notReady") }}</p>
      <p v-if="state?.error" class="text-coral whitespace-pre-wrap break-words">
        {{ state.error }}
      </p>
      <div v-if="lines.length" class="flex flex-col gap-1">
        <span class="section-title">{{ t("flow.log") }}</span>
        <div
          v-for="(entry, position) in lines"
          :key="position"
          class="flex items-center gap-2 font-mono text-[10px] text-warm-500"
        >
          <span>{{ when(entry) }}</span
          ><StatusDot :status="entry.status" /><span>{{ t(`flow.status.${entry.status}`) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
