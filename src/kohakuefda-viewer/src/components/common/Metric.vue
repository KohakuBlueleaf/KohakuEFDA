<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  hint: { type: String, default: "" },
  tone: { type: String, default: "" },
})
</script>

<template>
  <div class="flex flex-col gap-0.5 min-w-20">
    <span class="section-title">{{ label }}</span>
    <span
      class="text-lg font-medium tabular-nums leading-tight"
      :class="tone || 'text-warm-800 dark:text-warm-200'"
    >
      {{ value }}
    </span>
    <span v-if="hint" class="text-[10px] text-warm-400">{{ hint }}</span>
  </div>
</template>
