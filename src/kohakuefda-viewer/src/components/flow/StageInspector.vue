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

// The label is the short name; the tooltip is what the setting actually does. A key with no
// help of its own falls back to the label so nothing shows an empty tooltip.
function help(key) {
  const text = t(`paramHelp.${key}`)
  return text === `paramHelp.${key}` ? t(`params.${key}`) : text
}

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
const RANGES = [{ match: /./, min: 0, max: null }]

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
    key: "spread",
    match:
      /^(workers|spread_attempts|spread_slice|spread_gap|spread_widest|flow_order|frame_every)$/,
  },
  { key: "shrink", match: /^shrink_/ },
  {
    key: "space",
    match: /^(w_wire|w_unit|w_pull|w_shape|w_over|w_pylon|entry_sides|pylon)$/,
  },
  {
    key: "routing",
    match: /^(route_iterations|present_cost|present_growth|turn_cost|bridge_cost|history_cost)$/,
  },
]
const CHOICES = computed(() => ({
  entry_sides: ["NW", "N", "W", "NESW"],
  flow_order: ["bottom-up", "top-down"],
  solver: store.solvers.map((entry) => entry.name),
  backend: ["auto", "python", "native"],
}))

function choiceLabel(key, choice) {
  const label = t(`choices.${key}.${choice}`)
  return label === `choices.${key}.${choice}` ? choice : label
}

const PRIMARY = {
  layout: ["solver", "spread_attempts", "workers", "seed"],
}

const headline = computed(() => (PRIMARY[stage.value] ?? []).filter((key) => key in defaults.value))

const groups = computed(() => {
  const shown = new Set(headline.value)
  const keys = Object.keys(defaults.value).filter((key) => !shown.has(key))
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

// What the run is doing now, read off the frames it has sent.
const progress = computed(() => {
  const frames = store.run?.frames?.[stage.value] ?? []
  const last = frames[frames.length - 1]
  if (!active.value || !last) {
    return null
  }
  if (last.kind === "build") {
    return { phase: "spread", done: last.placed ?? 0, total: last.total ?? 0 }
  }
  if (last.kind === "improve") {
    return { phase: "improve", done: last.step ?? 0, total: last.of ?? 0 }
  }
  return { phase: last.kind, done: 0, total: 0 }
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
      <div v-if="progress" class="flex flex-col gap-1 rounded bg-warm-100 dark:bg-warm-800 p-2">
        <div class="flex items-center gap-2">
          <span class="font-medium">{{ t(`phase.${progress.phase}`) }}</span>
          <span class="flex-1" />
          <span v-if="progress.total" class="text-secondary tabular-nums">
            {{ progress.done }} / {{ progress.total }}
          </span>
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
      <div v-if="Object.keys(defaults).length" class="flex flex-col gap-1.5">
        <div class="flex items-center gap-2">
          <span class="section-title">{{ t("flow.params") }}</span>
          <span class="flex-1" />
          <button class="btn-secondary !text-[10px] !py-0.5" @click="store.resetDraft(stage)">
            {{ t("flow.reset") }}
          </button>
        </div>
        <div v-if="headline.length" class="flex flex-col gap-1.5 pb-1">
          <label v-for="key in headline" :key="key" class="flex items-center justify-between gap-2">
            <span class="font-medium text-warm-700 dark:text-warm-200" :title="help(key)">
              {{ t(`params.${key}`) }}
            </span>
            <select v-if="CHOICES[key]" v-model="params[key]" class="input-number !w-40">
              <option v-for="choice in CHOICES[key]" :key="choice" :value="choice">
                {{ choiceLabel(key, choice) }}
              </option>
            </select>
            <input
              v-else
              v-model="params[key]"
              type="number"
              :min="boundsOf(key).min"
              :max="boundsOf(key).max"
              :step="boundsOf(key).step"
              class="input-number !w-40"
              @change="clamp(key)"
            />
          </label>
          <p class="text-secondary leading-snug">{{ help(headline[0]) }}</p>
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
              <span class="text-warm-600 dark:text-warm-300" :title="help(key)">{{
                t(`params.${key}`)
              }}</span>
              <select v-if="CHOICES[key]" v-model="params[key]" class="input-number !w-32">
                <option v-for="choice in CHOICES[key]" :key="choice" :value="choice">
                  {{ choiceLabel(key, choice) }}
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
