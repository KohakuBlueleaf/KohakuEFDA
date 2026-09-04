<script setup>
import {
  drawArea,
  drawBackground,
  drawBlocks,
  drawCells,
  drawEntries,
  drawMarks,
  drawPath,
  drawPylons,
  drawRect,
  flowDimensions,
  itemColour,
  palette,
  sizeCanvas,
} from "@/draw"
import { useThemeStore } from "@/stores/theme"

const props = defineProps({
  dataset: { type: Object, required: true },
  mode: { type: String, default: "layout" },
  square: { type: Array, default: () => [50, 50] },
  cellSize: { type: Number, default: 12 },
  catalogue: { type: Object, default: null },
  frame: { type: Object, default: null },
  showLabels: { type: Boolean, default: true },
  showCoverage: { type: Boolean, default: true },
  lang: { type: String, default: "en" },
  fill: { type: Boolean, default: false },
  viewportScale: { type: Number, default: 1 },
  viewportOffsetX: { type: Number, default: 0 },
  viewportOffsetY: { type: Number, default: 0 },
})
const emit = defineEmits(["hover"])
const theme = useThemeStore()
const canvas = ref(null)

const dimensions = computed(() => flowDimensions(props.frame, props.catalogue, props.square))
const effectiveSize = computed(() => props.cellSize * (props.fill ? props.viewportScale : 1))

function drawWires(ctx, frame, size, p) {
  const items = frame.items ?? {}
  for (const [id, kind, net, cells] of frame.wires ?? []) {
    const pipe = kind === "pipe"
    const colour = itemColour(items[id] ?? net, p, pipe)
    drawPath(ctx, cells, size, colour, pipe ? 0.5 : 0.32, null, pipe)
  }
}

function draw() {
  const element = canvas.value
  if (!element) {
    return
  }
  const size = effectiveSize.value
  const p = palette(theme.dark)
  const [width, height] = dimensions.value
  const ctx = sizeCanvas(element, width * size, height * size)
  drawBackground(ctx, width, height, size, p)
  const catalogue = props.catalogue
  if (catalogue?.area) {
    drawArea(ctx, [width, height], catalogue.area, size, p)
    drawCells(
      ctx,
      (catalogue.slots ?? []).map(([x, y]) => [x, y]),
      size,
      p.slot,
    )
  }
  const frame = props.frame
  if (!catalogue || !frame?.blocks) {
    return
  }
  if (frame.rect) {
    drawRect(ctx, frame.rect, size, p.selection)
  }
  drawPylons(ctx, frame.pylons ?? [], props.dataset.pylons?.power_diffuser_1?.reach ?? 5, size, p, {
    showCoverage: props.showCoverage,
  })
  drawBlocks(ctx, props.dataset, catalogue.blocks, frame.blocks, size, p, {
    showLabels: props.showLabels && size >= 10,
    lang: props.lang,
  })
  drawEntries(ctx, frame.entries ?? [], props.dataset, size, p, props.lang, props.showLabels)
  drawWires(ctx, frame, size, p)
}

function onMove(event) {
  const rect = canvas.value.getBoundingClientRect()
  emit("hover", {
    x: Math.floor((event.clientX - rect.left) / effectiveSize.value),
    y: Math.floor((event.clientY - rect.top) / effectiveSize.value),
  })
}

onMounted(draw)
watch(
  () => [
    props.mode,
    props.square,
    props.catalogue,
    props.frame,
    props.showLabels,
    props.showCoverage,
    props.lang,
    theme.dark,
    effectiveSize.value,
  ],
  draw,
)
</script>

<template>
  <div :class="fill ? 'relative overflow-hidden w-full h-full' : 'overflow-auto card max-h-[65vh]'">
    <canvas
      ref="canvas"
      :class="fill ? 'absolute top-0 left-0 block cursor-grab' : 'block'"
      :style="fill ? { transform: `translate(${viewportOffsetX}px, ${viewportOffsetY}px)` } : null"
      @mousemove="onMove"
      @mouseleave="emit('hover', null)"
    />
  </div>
</template>
