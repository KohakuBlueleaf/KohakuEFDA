<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()

const TERMS = [
  "area",
  "width",
  "height",
  "waste",
  "length",
  "junctions",
  "pylons",
  "bricks_underused",
]
const BAD = new Set(["waste", "bricks_underused"])

const steps = computed(() =>
  store.frames.layout.filter((f) => f && (f.kind === "build" || f.kind === "improve")),
)
const chart = computed(() => ({
  cursor: Math.max(0, steps.value.length - 1),
  series: [
    { label: t("flow.cost"), colour: "#D4920A", values: steps.value.map((f) => f.cost) },
    {
      label: t("flow.wire"),
      colour: "#4C9989",
      values: steps.value.map((f) => f.wires.reduce((n, w) => n + w[3].length, 0)),
    },
  ],
}))
const terms = computed(() => {
  const source = store.placement?.terms ?? steps.value.at(-1)?.terms
  if (!source) {
    return []
  }
  return TERMS.filter((key) => key in source).map((key) => ({
    key,
    label: t(`terms.${key}`),
    value: source[key],
    bad: BAD.has(key) && source[key] > 0,
  }))
})
</script>

<template>
  <div v-if="chart.series[0].values.length || terms.length" class="flex flex-col gap-1.5">
    <span class="section-title">{{ t("flow.costCurve") }}</span>
    <CostChart
      v-if="chart.series[0].values.length"
      :series="chart.series"
      :cursor="chart.cursor"
      :width="252"
      :height="96"
    />
    <div v-if="terms.length" class="card p-2 flex flex-col gap-1 text-xs">
      <div
        v-for="term in terms"
        :key="term.key"
        class="flex items-baseline justify-between gap-2"
        :class="term.bad ? 'text-coral' : ''"
      >
        <span class="text-secondary" :class="term.bad ? '!text-coral' : ''">{{ term.label }}</span>
        <span class="font-mono tabular-nums">{{
          Number.isInteger(term.value) ? term.value : term.value.toFixed(1)
        }}</span>
      </div>
    </div>
  </div>
</template>
