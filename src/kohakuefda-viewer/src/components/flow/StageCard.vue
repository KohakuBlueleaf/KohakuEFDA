<script setup>
import { useI18n } from "@/i18n"

const props = defineProps({
  stage: { type: String, required: true },
  position: { type: Number, default: 0 },
  state: { type: Object, default: null },
  ready: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  last: { type: Boolean, default: false },
})
const emit = defineEmits(["run", "run-through", "cancel", "select"])
const { t } = useI18n()
const ICON = {
  plan: "i-carbon-chart-relationship",
  netlist: "i-carbon-assembly-cluster",
  layout: "i-carbon-apps",
  verify: "i-carbon-checkmark-outline",
}

const status = computed(() => props.state?.status ?? "idle")
const active = computed(() => status.value === "running" || status.value === "queued")
const duration = computed(() => {
  const { started, finished } = props.state ?? {}
  if (!started || !finished) {
    return ""
  }
  return `${(finished - started).toFixed(1)}s`
})
</script>

<template>
  <button
    class="card text-left px-3 py-2 min-w-40 flex-1 transition-colors"
    :class="[
      selected ? 'border-iolite dark:border-iolite-light ring-1 ring-iolite/30' : '',
      active ? 'bg-aquamarine/5' : '',
    ]"
    @click="emit('select', stage)"
  >
    <div class="flex items-center gap-2">
      <span class="text-[10px] font-mono text-warm-400">{{ position + 1 }}</span>
      <span :class="ICON[stage]" class="text-[14px] text-iolite" />
      <span class="text-xs font-medium text-warm-800 dark:text-warm-200">{{
        t(`stage.${stage}`)
      }}</span>
      <span class="flex-1" />
      <StatusDot :status="status" />
    </div>
    <div class="flex items-center gap-1 mt-1 text-[10px] text-warm-500">
      <span>{{ t(`flow.status.${status}`) }}</span>
      <span v-if="duration" class="font-mono">· {{ duration }}</span>
      <span class="flex-1" />
      <template v-if="active">
        <button
          class="btn-icon !w-6 !h-6 text-coral"
          :title="t('flow.cancel')"
          @click.stop="emit('cancel')"
        >
          <span class="i-carbon-stop-filled-alt text-[11px]" />
        </button>
      </template>
      <template v-else>
        <button
          class="btn-icon !w-6 !h-6"
          :disabled="!ready || busy"
          :title="t('flow.run')"
          @click.stop="emit('run', stage)"
        >
          <span class="i-carbon-play-filled-alt text-[11px]" />
        </button>
        <button
          v-if="!last"
          class="btn-icon !w-6 !h-6"
          :disabled="!ready || busy"
          :title="t('flow.runThrough')"
          @click.stop="emit('run-through', stage)"
        >
          <span class="i-carbon-skip-forward-filled text-[11px]" />
        </button>
      </template>
    </div>
  </button>
</template>
