<script setup>
import { useI18n } from "@/i18n"
import { formatRate } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const open = ref("")
const GROUPS = [
  { kind: "delivered", icon: "i-carbon-checkmark-filled", tone: "text-sage" },
  { kind: "stored", icon: "i-carbon-box", tone: "text-warm-500" },
  { kind: "dumped", icon: "i-carbon-rain-drop", tone: "text-taaffeite" },
  { kind: "consumed", icon: "i-carbon-arrow-down", tone: "text-sapphire" },
  { kind: "missing", icon: "i-carbon-warning-alt", tone: "text-coral" },
]
const GOAL_CHIP = { min: "chip-iolite", max: "chip-aqua" }

const groups = computed(() =>
  GROUPS.map((group) => ({
    ...group,
    items: store.outcomes.filter((o) => o.kind === group.kind),
  })).filter((group) => group.items.length),
)

function key(outcome) {
  return `${outcome.kind}:${outcome.item_id}`
}

function toggle(outcome) {
  open.value = open.value === key(outcome) ? "" : key(outcome)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div v-for="group in groups" :key="group.kind" class="flex flex-col gap-1.5">
      <h3 class="flex items-center gap-1.5 text-xs font-medium" :class="group.tone">
        <span :class="group.icon" />
        {{ t(`outcomes.${group.kind}`) }}
        <span class="text-secondary font-normal">· {{ t(`outcomes.${group.kind}Hint`) }}</span>
      </h3>
      <div class="flex flex-wrap gap-2">
        <div
          v-for="outcome in group.items"
          :key="key(outcome)"
          class="card p-2 flex items-center gap-2 relative min-w-56 group"
        >
          <EntityIcon
            :id="outcome.item_id"
            kind="items"
            :size="40"
            show-name
            class="flex-1 min-w-0 text-xs font-medium"
          />
          <div class="flex flex-col items-end gap-0.5">
            <span class="font-mono text-xs tabular-nums">
              {{ formatRate(outcome.rate) }}<span class="text-warm-400">/min</span>
            </span>
            <span v-if="outcome.goal" :class="GOAL_CHIP[outcome.goal]">{{
              t(`entry.intent.${outcome.goal}`)
            }}</span>
            <EntityIcon
              v-if="outcome.sink_machine"
              :id="outcome.sink_machine"
              kind="machines"
              :size="18"
              show-name
              class="text-[10px] text-warm-500"
            />
          </div>
          <button
            v-if="outcome.next.length"
            class="btn-ghost !text-[11px] hover-only-action text-iolite"
            @click="toggle(outcome)"
          >
            {{ t("outcomes.useIt") }} <span class="i-carbon-arrow-right" />
          </button>
          <div v-if="open === key(outcome)" class="absolute left-0 top-full mt-1 z-30">
            <NextProducts :outcome="outcome" @close="open = ''" />
          </div>
        </div>
      </div>
    </div>
    <p v-if="!groups.length" class="text-secondary">{{ t("outcomes.noPlan") }}</p>
  </div>
</template>
