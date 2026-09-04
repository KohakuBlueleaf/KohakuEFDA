<script setup>
import { useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const props = defineProps({
  kind: { type: String, default: "items" },
  id: { type: String, required: true },
  size: { type: Number, default: 28 },
  showName: { type: Boolean, default: false },
})
const store = useAppStore()
const names = useNames()

const url = computed(() => store.iconUrl(props.kind, props.id))
const name = computed(() => {
  const table = { items: names.item, machines: names.machine, logistics: names.unit }
  return (table[props.kind] ?? names.item)(props.id)
})
const glyph = computed(() => {
  if (props.kind === "machines") {
    return "i-carbon-industry"
  }
  if (props.kind === "logistics") {
    return "i-carbon-flow"
  }
  const phase = store.dataset?.items?.[props.id]?.phase
  if (phase === 2) {
    return "i-carbon-rain-drop"
  }
  if (phase === 4) {
    return "i-carbon-cloud"
  }
  return "i-carbon-cube"
})
const box = computed(() => ({ width: `${props.size}px`, height: `${props.size}px` }))
</script>

<template>
  <span class="inline-flex items-center gap-1.5 min-w-0">
    <span
      class="inline-flex items-center justify-center rounded-md shrink-0 overflow-hidden bg-warm-100 dark:bg-warm-800"
      :style="box"
      :title="name"
    >
      <img v-if="url" :src="url" :alt="name" class="w-full h-full object-contain" loading="lazy" />
      <span v-else :class="glyph" class="text-warm-400" :style="{ fontSize: `${size * 0.55}px` }" />
    </span>
    <span v-if="showName" class="truncate">{{ name }}</span>
  </span>
</template>
