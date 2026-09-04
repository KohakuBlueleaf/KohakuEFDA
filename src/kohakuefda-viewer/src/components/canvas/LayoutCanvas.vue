<script setup>
import { buildIndex, drawBackground, drawLayout, palette, sizeCanvas } from "@/draw"
import { useThemeStore } from "@/stores/theme"

const props = defineProps({
  layout: { type: Object, required: true },
  dataset: { type: Object, required: true },
  cellSize: { type: Number, default: 14 },
  showGround: { type: Boolean, default: true },
  showSky: { type: Boolean, default: true },
  showModules: { type: Boolean, default: false },
  showLabels: { type: Boolean, default: true },
  showItems: { type: Boolean, default: true },
  showBadges: { type: Boolean, default: true },
  showCoverage: { type: Boolean, default: false },
  highlight: { type: String, default: "" },
  lang: { type: String, default: "en" },
  fill: { type: Boolean, default: false },
  viewportScale: { type: Number, default: 1 },
  viewportOffsetX: { type: Number, default: 0 },
  viewportOffsetY: { type: Number, default: 0 },
})
const emit = defineEmits(["hover"])
const theme = useThemeStore()

const canvas = ref(null)
const index = computed(() => buildIndex(props.layout, props.dataset))
const effectiveSize = computed(() => props.cellSize * (props.fill ? props.viewportScale : 1))

function draw() {
  const element = canvas.value
  if (!element) {
    return
  }
  const size = effectiveSize.value
  const p = palette(theme.dark)
  const ctx = sizeCanvas(element, props.layout.width * size, props.layout.height * size)
  drawBackground(ctx, props.layout.width, props.layout.height, size, p)
  drawLayout(ctx, props.layout, props.dataset, size, p, {
    showGround: props.showGround,
    showSky: props.showSky,
    showLabels: props.showLabels,
    showItems: props.showItems,
    showModules: props.showModules,
    showBadges: props.showBadges,
    showCoverage: props.showCoverage,
    highlight: props.highlight,
    lang: props.lang,
  })
}

function onMove(event) {
  const rect = canvas.value.getBoundingClientRect()
  const x = Math.floor((event.clientX - rect.left) / effectiveSize.value)
  const y = Math.floor((event.clientY - rect.top) / effectiveSize.value)
  const key = `${x},${y}`
  const hit =
    (props.showSky ? index.value.sky.get(key) : null) ??
    (props.showGround ? index.value.ground.get(key) : null) ??
    null
  emit("hover", { x, y, hit })
}

onMounted(draw)
watch(
  () => [
    props.layout,
    props.showGround,
    props.showSky,
    props.showModules,
    props.showLabels,
    props.showItems,
    props.showBadges,
    props.showCoverage,
    props.highlight,
    props.lang,
    theme.dark,
    effectiveSize.value,
  ],
  draw,
  { deep: true },
)
</script>

<template>
  <div :class="fill ? 'relative overflow-hidden w-full h-full' : 'overflow-auto card max-h-[70vh]'">
    <canvas
      ref="canvas"
      :class="fill ? 'absolute top-0 left-0 block cursor-grab' : 'block'"
      :style="fill ? { transform: `translate(${viewportOffsetX}px, ${viewportOffsetY}px)` } : null"
      @mousemove="onMove"
      @mouseleave="emit('hover', null)"
    />
  </div>
</template>
