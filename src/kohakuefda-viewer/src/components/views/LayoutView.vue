<script setup>
import { useTimeline } from "@/composables/timeline"
import { useViewport } from "@/composables/viewport"
import { flowDimensions } from "@/draw"
import { useI18n } from "@/i18n"
import { useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const names = useNames()
const store = useAppStore()
const cellSize = ref(12)
const showLabels = ref(true)
const showItems = ref(true)
const showCoverage = ref(true)
const showFinal = ref(true)
const hover = ref(null)
const stageEl = ref(null)

const catalogue = computed(() => store.frames.layout.find((f) => f?.kind === "catalogue") ?? null)
const frames = computed(() => store.frames.layout.filter((f) => f && f.kind !== "catalogue"))
const { index, playing, speed, live } = useTimeline(frames)
const frame = computed(() => frames.value[Math.min(index.value, frames.value.length - 1)] ?? null)
const finalReady = computed(() => Boolean(store.layout) && showFinal.value)
const gridSize = computed(() =>
  finalReady.value && store.layout
    ? [store.layout.width, store.layout.height]
    : flowDimensions(frame.value, catalogue.value, store.square ?? [50, 50]),
)
const contentSize = computed(() => [
  gridSize.value[0] * cellSize.value,
  gridSize.value[1] * cellSize.value,
])
const viewport = useViewport(stageEl, contentSize)

const label = computed(() => {
  const f = frame.value
  if (!f) {
    return ""
  }
  if (f.kind === "build" || f.kind === "improve") {
    const size = `${f.rect[2] - f.rect[0]}×${f.rect[3] - f.rect[1]}`
    const done = `${f.placed ?? f.blocks.length}/${f.total ?? f.blocks.length}`
    return `${t(f.kind === "build" ? "flow.building" : "flow.improving")} · ${done} · ${size} · ${t("flow.cost")} ${f.cost.toFixed(0)}`
  }
  return `${t("flow.final")} · ${f.fits ? t("flow.fits") : t("flow.tooBig")}`
})
</script>

<template>
  <div class="h-full flex flex-col gap-2 min-h-0">
    <div class="flex items-center gap-3 flex-wrap text-xs shrink-0">
      <label v-if="store.layout" class="flex items-center gap-1"
        ><input v-model="showFinal" type="checkbox" class="accent-iolite" />
        {{ t("flow.showFinal") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showLabels" type="checkbox" class="accent-iolite" />
        {{ t("layout.labels") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showItems" type="checkbox" class="accent-iolite" />
        {{ t("layout.items") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showCoverage" type="checkbox" class="accent-iolite" />
        {{ t("layout.coverage") }}</label
      >
      <label class="flex items-center gap-1"
        >{{ t("layout.cell") }}
        <input v-model.number="cellSize" type="range" min="4" max="28" class="accent-iolite"
      /></label>
      <span class="text-warm-400 font-mono">{{ hover ? `(${hover.x}, ${hover.y})` : "" }}</span>
      <span class="flex-1" />
      <span v-if="!frames.length && !store.layout" class="text-secondary">{{
        t("flow.noFrames")
      }}</span>
    </div>
    <div class="flex-1 min-h-0 flex gap-3">
      <div
        ref="stageEl"
        class="relative flex-1 min-w-0 h-full overflow-hidden card touch-none cursor-grab"
        @wheel="viewport.onWheel"
        @pointerdown="viewport.onPointerDown"
        @dblclick="viewport.reset"
        @touchstart="viewport.onTouchStart"
        @touchmove="viewport.onTouchMove"
        @touchend="viewport.onTouchEnd"
        @touchcancel="viewport.onTouchEnd"
      >
        <LayoutCanvas
          v-if="finalReady && store.dataset"
          :layout="store.layout"
          :dataset="store.dataset"
          :cell-size="cellSize"
          :show-labels="showLabels"
          :show-items="showItems"
          :show-coverage="showCoverage"
          :lang="names.lang.value"
          fill
          :viewport-scale="viewport.scale"
          :viewport-offset-x="viewport.offsetX"
          :viewport-offset-y="viewport.offsetY"
          @hover="hover = $event"
        />
        <FlowCanvas
          v-else-if="store.dataset"
          :dataset="store.dataset"
          mode="layout"
          :square="store.square ?? [50, 50]"
          :cell-size="cellSize"
          :catalogue="catalogue"
          :frame="frame"
          :show-labels="showLabels"
          :show-coverage="showCoverage"
          :lang="names.lang.value"
          fill
          :viewport-scale="viewport.scale"
          :viewport-offset-x="viewport.offsetX"
          :viewport-offset-y="viewport.offsetY"
          @hover="hover = $event"
        />
        <div class="absolute bottom-2 right-2 flex flex-col gap-0.5 card p-0.5">
          <button class="btn-icon" :title="t('viewport.zoomIn')" @click="viewport.zoomIn">
            <span class="i-carbon-zoom-in" />
          </button>
          <button class="btn-icon" :title="t('viewport.zoomOut')" @click="viewport.zoomOut">
            <span class="i-carbon-zoom-out" />
          </button>
          <button class="btn-icon" :title="t('viewport.fit')" @click="viewport.fit">
            <span class="i-carbon-fit-to-screen" />
          </button>
        </div>
      </div>
    </div>
    <Timeline
      v-model:index="index"
      v-model:playing="playing"
      v-model:speed="speed"
      v-model:live="live"
      :count="frames.length"
      :label="label"
      class="shrink-0"
    />
  </div>
</template>
