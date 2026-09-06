<script setup>
const props = defineProps({
  status: { type: String, default: "idle" },
})

const colour = computed(
  () =>
    ({
      running: "bg-aquamarine kohaku-pulse",
      queued: "bg-aquamarine",
      done: "bg-aquamarine",
      idle: "bg-warm-400",
      failed: "bg-coral",
      incomplete: "bg-amber",
      cancelled: "bg-amber",
    })[props.status] ?? "bg-warm-400",
)
</script>

<template>
  <span class="inline-block w-2 h-2 rounded-full shrink-0" :class="colour" :title="status" />
</template>
