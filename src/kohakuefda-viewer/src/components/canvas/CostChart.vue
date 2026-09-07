<script setup>
import { chartGeometry } from "@/progress"
const props = defineProps({
  series: { type: Array, default: () => [] },
  cursor: { type: Number, default: -1 },
  title: { type: String, default: "" },
  width: { type: Number, default: 300 },
  height: { type: Number, default: 110 },
})

const scaled = computed(() => chartGeometry(props.series, props.width, props.height, props.cursor))
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
      <path
        v-for="line in scaled.lines"
        :key="line.label"
        :d="line.path"
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
