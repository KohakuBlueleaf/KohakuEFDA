<script setup>
import { useI18n } from "@/i18n"
import { STAGES, useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()

const stage = computed(() => store.selectedStage)
const state = computed(() => store.run?.stages?.[stage.value] ?? null)
const defaults = computed(() => store.params[stage.value] ?? {})
const params = computed(() => store.draftParams(stage.value))
const status = computed(() => state.value?.status ?? "idle")
const active = computed(() => ["running", "queued"].includes(status.value))
const ready = computed(() => {
  const position = STAGES.indexOf(stage.value)
  return (
    Boolean(store.run) && STAGES.slice(0, position).every((s) => store.stageStatus(s) === "done")
  )
})
const lines = computed(() => store.log.filter((entry) => entry.stage === stage.value).reverse())

function isText(key) {
  return typeof defaults.value[key] === "string"
}

function collect() {
  const out = {}
  for (const key of Object.keys(defaults.value)) {
    const value = params.value[key]
    out[key] = isText(key) ? String(value) : Number(value)
  }
  return out
}

// Every numeric setting spans its whole legal range: shares and probabilities 0..1,
// counts and weights 0 and up; floats step freely.
const RANGES = [
  { match: /^(p_|route_from$|reheat$)/, min: 0, max: 1 },
  { match: /./, min: 0, max: null },
]

function boundsOf(key) {
  const range = RANGES.find((r) => r.match.test(key))
  const integer = Number.isInteger(defaults.value[key])
  return {
    min: range.min,
    max: range.max ?? undefined,
    step: integer ? 1 : "any",
  }
}

function clamp(key) {
  const { min, max } = boundsOf(key)
  const value = Number(params.value[key])
  if (Number.isNaN(value)) {
    params.value[key] = defaults.value[key]
    return
  }
  if (value < min) {
    params.value[key] = min
  } else if (max !== undefined && value > max) {
    params.value[key] = max
  } else if (Number.isInteger(defaults.value[key])) {
    params.value[key] = Math.round(value)
  } else {
    params.value[key] = value
  }
}

const GROUPS = [
  {
    key: "search",
    match:
      /^(seed|spread_attempts|spread_gap|spread_widest|flow_order|workers|candidate_tries|frame_every)$/,
  },
  {
    key: "space",
    match:
      /^(w_wire|w_unit|w_pull|w_shape|w_over|w_pylon|max_gap|enlarge_rounds|enlarge_step|entry_sides|pylon)$/,
  },
  { key: "moves", match: /^move_/ },
  {
    key: "routing",
    match: /^(route_iterations|present_cost|present_growth|turn_cost|bridge_cost|history_cost)$/,
  },
]
const CHOICES = {
  entry_sides: ["NW", "N", "W", "NESW"],
}

const groups = computed(() => {
  const keys = Object.keys(defaults.value)
  const out = []
  for (const group of GROUPS) {
    const members = keys.filter((key) => group.match.test(key))
    if (members.length) {
      out.push({ key: group.key, members })
    }
  }
  const placed = new Set(out.flatMap((g) => g.members))
  const rest = keys.filter((key) => !placed.has(key))
  if (rest.length) {
    out.push({ key: "other", members: rest })
  }
  return out
})

function when(entry) {
  const time = entry.finished ?? entry.started ?? entry.time
  return new Date(time * 1000).toLocaleTimeString()
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
      <LayoutCost v-if="stage === 'layout'" />
      <div v-if="Object.keys(defaults).length" class="flex flex-col gap-1.5">
        <div class="flex items-center gap-2">
          <span class="section-title">{{ t("flow.params") }}</span>
          <span class="flex-1" />
          <button class="btn-secondary !text-[10px] !py-0.5" @click="store.resetDraft(stage)">
            {{ t("flow.reset") }}
          </button>
        </div>
        <details v-for="group in groups" :key="group.key" :open="group.key === 'search'">
          <summary class="text-[10px] uppercase tracking-wide text-warm-500 cursor-pointer">
            {{ t(`paramGroup.${group.key}`) }}
          </summary>
          <div class="flex flex-col gap-1 mt-1">
            <label
              v-for="key in group.members"
              :key="key"
              class="flex items-center justify-between gap-2"
            >
              <span class="text-warm-600 dark:text-warm-300" :title="t(`params.${key}`)">{{
                t(`params.${key}`)
              }}</span>
              <select v-if="CHOICES[key]" v-model="params[key]" class="input-number !w-32">
                <option v-for="choice in CHOICES[key]" :key="choice" :value="choice">
                  {{ t(`choices.${key}.${choice}`) }}
                </option>
              </select>
              <input
                v-else-if="isText(key)"
                v-model="params[key]"
                type="text"
                class="input-number !w-32"
              />
              <input
                v-else
                v-model="params[key]"
                type="number"
                :min="boundsOf(key).min"
                :max="boundsOf(key).max"
                :step="boundsOf(key).step"
                class="input-number"
                @change="clamp(key)"
              />
            </label>
          </div>
        </details>
      </div>
      <div class="flex gap-1.5 flex-wrap">
        <button v-if="active" class="btn-secondary !text-xs text-coral" @click="store.cancelRun()">
          <span class="i-carbon-stop-filled-alt" /> {{ t("flow.cancel") }}
        </button>
        <template v-else>
          <button
            class="btn-primary !text-xs"
            :disabled="!ready || store.runBusy"
            @click="store.startStage(stage, collect())"
          >
            <span class="i-carbon-play-filled-alt" /> {{ t("flow.run") }}
          </button>
          <button
            v-if="stage !== 'verify'"
            class="btn-secondary !text-xs"
            :disabled="!ready || store.runBusy"
            @click="store.startStage(stage, collect(), 'verify')"
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
          <span>{{ when(entry) }}</span>
          <StatusDot :status="entry.status" />
          <span>{{ t(`flow.status.${entry.status}`) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
