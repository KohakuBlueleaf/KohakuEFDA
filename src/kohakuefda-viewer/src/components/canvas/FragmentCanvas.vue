<script setup>
import { drawBackground, drawLayout, palette, sizeCanvas } from "@/draw"
import { useThemeStore } from "@/stores/theme"

const props = defineProps({
  fragment: { type: Object, required: true },
  dataset: { type: Object, required: true },
  maxWidth: { type: Number, default: 260 },
  lang: { type: String, default: "en" },
})
const theme = useThemeStore()
const canvas = ref(null)

function draw() {
  const element = canvas.value
  if (!element) {
    return
  }
  const size = Math.max(4, Math.min(14, Math.floor(props.maxWidth / props.fragment.width)))
  const p = palette(theme.dark)
  const ctx = sizeCanvas(element, props.fragment.width * size, props.fragment.height * size)
  drawBackground(ctx, props.fragment.width, props.fragment.height, size, p)
  drawLayout(
    ctx,
    { ...props.fragment, modules: [], units: [], segments: [], entries: [] },
    props.dataset,
    size,
    p,
    { showLabels: false, showBadges: size >= 8, lang: props.lang },
  )
}

onMounted(draw)
watch(() => [props.fragment, props.maxWidth, theme.dark], draw)
</script>

<template>
  <canvas ref="canvas" class="block rounded-md" />
</template>
