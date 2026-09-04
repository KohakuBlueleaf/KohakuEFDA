<script setup>
const props = defineProps({
  series: { type: Array, default: () => [] },
  cursor: { type: Number, default: -1 },
  title: { type: String, default: "" },
  width: { type: Number, default: 300 },
  height: { type: Number, default: 110 },
})

const PAD = 4

const scaled = computed(() => {
  const all = props.series.flatMap((s) => s.values)
  if (!all.length) {
    return { lines: [], min: 0, max: 0, cursorX: null }
  }
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 1
  const count = Math.max(...props.series.map((s) => s.values.length), 1)
  const sx = (props.width - 2 * PAD) / Math.max(count - 1, 1)
  const sy = (props.height - 2 * PAD) / span
  const lines = props.series.map((s) => ({
    colour: s.colour,
    label: s.label,
    points: s.values
      .map(
        (v, i) =>
          `${(PAD + i * sx).toFixed(1)},${(props.height - PAD - (v - min) * sy).toFixed(1)}`,
      )
      .join(" "),
  }))
  const cursorX = props.cursor >= 0 ? PAD + props.cursor * sx : null
  return { lines, min, max, cursorX }
})
</script>

<template>
  <div class="card p-2">
    <div class="flex justify-between text-[10px] text-warm-500 mb-1">
      <span class="section-title">{{ title }}</span>
      <span class="flex gap-2">
        <span v-for="line in scaled.lines" :key="line.label" :style="{ color: line.colour }">
          {{ line.label }}
        </span>
      </span>
    </div>
    <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" class="max-w-full">
      <rect x="0" y="0" :width="width" :height="height" rx="6" class="plot" />
      <polyline
        v-for="line in scaled.lines"
        :key="line.label"
        :points="line.points"
        fill="none"
        :stroke="line.colour"
        stroke-width="1.5"
        stroke-linejoin="round"
      />
      <line
        v-if="scaled.cursorX !== null"
        :x1="scaled.cursorX"
        :x2="scaled.cursorX"
        y1="0"
        :y2="height"
        stroke="#D4920A"
        stroke-width="1"
      />
    </svg>
    <div class="flex justify-between text-[10px] text-warm-400 font-mono">
      <span>{{ scaled.min.toFixed(1) }}</span>
      <span>{{ scaled.max.toFixed(1) }}</span>
    </div>
  </div>
</template>

<style scoped>
.plot {
  fill: var(--canvas-bg);
}
</style>
