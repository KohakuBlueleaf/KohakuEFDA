<script setup>
import { progressFrames } from "@/progress"
import { useAppStore } from "@/stores/app"

const store = useAppStore()
const frames = computed(() => progressFrames(store.frames.layout))
</script>

<template>
  <LayoutProgress :frame="frames.at(-1) ?? null" :frames="frames" />
</template>
