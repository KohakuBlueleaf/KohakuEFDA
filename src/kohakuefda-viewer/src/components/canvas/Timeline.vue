<script setup>
import { useI18n } from "@/i18n"

const props = defineProps({
  count: { type: Number, default: 0 },
  index: { type: Number, default: 0 },
  playing: { type: Boolean, default: false },
  speed: { type: Number, default: 1 },
  live: { type: Boolean, default: true },
  label: { type: String, default: "" },
})
const emit = defineEmits(["update:index", "update:playing", "update:speed", "update:live"])
const { t } = useI18n()
const SPEEDS = [1, 2, 4, 8, 16, 32]

function seek(value) {
  emit("update:live", false)
  emit("update:index", Number(value))
}

function step(delta) {
  seek(Math.min(Math.max(props.index + delta, 0), Math.max(props.count - 1, 0)))
}
</script>

<template>
  <div class="flex items-center gap-2 flex-wrap mt-2 text-xs">
    <button class="btn-icon" :disabled="count === 0" @click="emit('update:playing', !playing)">
      <span :class="playing ? 'i-carbon-pause-filled' : 'i-carbon-play-filled-alt'" />
    </button>
    <button class="btn-icon" :disabled="index <= 0" @click="step(-1)">
      <span class="i-carbon-chevron-left" />
    </button>
    <input
      type="range"
      class="flex-1 min-w-40 accent-iolite"
      min="0"
      :max="Math.max(count - 1, 0)"
      :value="index"
      :disabled="count === 0"
      @input="seek($event.target.value)"
    />
    <button class="btn-icon" :disabled="index >= count - 1" @click="step(1)">
      <span class="i-carbon-chevron-right" />
    </button>
    <span class="font-mono tabular-nums text-warm-500 min-w-20">
      {{ count ? index + 1 : 0 }} / {{ count }}
    </span>
    <select
      class="select-field !py-0.5 !text-xs"
      :value="speed"
      @change="emit('update:speed', Number($event.target.value))"
    >
      <option v-for="value in SPEEDS" :key="value" :value="value">{{ value }}×</option>
    </select>
    <label class="flex items-center gap-1 text-warm-600 dark:text-warm-300">
      <input
        type="checkbox"
        class="accent-iolite"
        :checked="live"
        @change="emit('update:live', $event.target.checked)"
      />
      {{ t("flow.live") }}
    </label>
    <span class="text-warm-500 font-mono text-[11px] w-full sm:w-auto">{{ label }}</span>
  </div>
</template>
