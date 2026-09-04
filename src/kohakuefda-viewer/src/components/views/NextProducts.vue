<script setup>
import { useI18n } from "@/i18n"
import { formatRate } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const props = defineProps({
  outcome: { type: Object, required: true },
})
const emit = defineEmits(["close"])
const { t } = useI18n()
const store = useAppStore()
const chosen = ref(null)
const intent = ref("rate")
const busy = ref(false)

async function apply(replace) {
  if (!chosen.value) {
    return
  }
  busy.value = true
  await store.extend(props.outcome, chosen.value, intent.value, replace)
  busy.value = false
  emit("close")
}
</script>

<template>
  <div class="card shadow-xl p-3 w-80 max-w-[90vw] flex flex-col gap-2 text-xs">
    <div class="flex items-center gap-2">
      <span class="font-medium">{{ t("next.title") }}</span>
      <span class="flex-1" />
      <button class="btn-icon !w-6 !h-6" @click="emit('close')">
        <span class="i-carbon-close text-[11px]" />
      </button>
    </div>
    <p v-if="!outcome.next.length" class="text-secondary">{{ t("next.none") }}</p>
    <div v-else class="flex flex-col gap-1 max-h-64 overflow-y-auto">
      <button
        v-for="option in outcome.next"
        :key="`${option.recipe_id}:${option.product_id}`"
        class="flex items-center gap-2 p-1.5 rounded-lg text-left hover:bg-warm-100 dark:hover:bg-warm-800 transition-colors"
        :class="chosen === option ? 'bg-iolite/10 ring-1 ring-iolite/40' : ''"
        @click="chosen = option"
      >
        <EntityIcon
          :id="option.product_id"
          kind="items"
          :size="30"
          show-name
          class="flex-1 min-w-0 font-medium"
        />
        <EntityIcon :id="option.machine_id" kind="machines" :size="22" />
        <span class="font-mono text-warm-500 whitespace-nowrap"
          >{{ formatRate(option.rate) }}/min</span
        >
      </button>
    </div>
    <template v-if="chosen">
      <p v-if="chosen.inputs.length" class="text-secondary flex items-center gap-1 flex-wrap">
        {{ t("next.needs") }}
        <EntityIcon
          v-for="input in chosen.inputs"
          :id="input"
          :key="input"
          kind="items"
          :size="18"
          show-name
        />
      </p>
      <div class="seg-group self-start">
        <button
          v-for="option in ['rate', 'min', 'max']"
          :key="option"
          :class="intent === option ? 'seg-item-active' : 'seg-item'"
          :title="t(`entry.intentHint.${option}`)"
          @click="intent = option"
        >
          {{
            option === "rate"
              ? t("next.matching", { rate: formatRate(chosen.rate) })
              : t(`entry.intent.${option}`)
          }}
        </button>
      </div>
      <div class="flex gap-1.5">
        <button
          class="btn-primary !text-xs flex-1 justify-center"
          :disabled="busy"
          @click="apply(false)"
        >
          <span class="i-carbon-add" /> {{ t("next.add") }}
        </button>
        <button
          v-if="outcome.kind === 'delivered'"
          class="btn-secondary !text-xs flex-1 justify-center"
          :disabled="busy"
          @click="apply(true)"
        >
          <span class="i-carbon-arrow-right" /> {{ t("next.extend") }}
        </button>
      </div>
    </template>
  </div>
</template>
