<script setup>
import { useI18n } from "@/i18n"
import { makeableItems } from "@/rules"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const pickerOpen = ref(false)
const INTENTS = ["min", "max", "rate"]

const targets = computed(() => Object.keys(store.scenario.targets))
const makeable = computed(() => (store.dataset ? makeableItems(store.dataset, store.scenario) : []))

function intentOf(item) {
  const spec = store.scenario.targets[item]
  return spec === "min" || spec === "max" ? spec : "rate"
}

function rateOf(item) {
  const spec = store.scenario.targets[item]
  return spec === "min" || spec === "max" ? "" : String(spec ?? "")
}

function setIntent(item, intent) {
  if (intent === "rate") {
    store.scenario.targets[item] = rateOf(item) || "30"
  } else {
    store.scenario.targets[item] = intent
  }
}

function setRate(item, value) {
  store.scenario.targets[item] = value.trim() || "0"
}

function add(item) {
  store.scenario.targets[item] = "min"
  store.refreshRequirements()
}

function remove(item) {
  delete store.scenario.targets[item]
  store.refreshRequirements()
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <p v-if="!targets.length" class="text-secondary">{{ t("entry.noTargets") }}</p>
    <div v-for="item in targets" :key="item" class="card p-2 flex flex-col gap-1.5">
      <div class="flex items-center gap-2">
        <EntityIcon
          :id="item"
          kind="items"
          :size="32"
          show-name
          class="flex-1 min-w-0 text-xs font-medium"
        />
        <button class="btn-icon !w-6 !h-6" :title="t('entry.remove')" @click="remove(item)">
          <span class="i-carbon-close text-[11px]" />
        </button>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <div class="seg-group">
          <button
            v-for="intent in INTENTS"
            :key="intent"
            :class="intentOf(item) === intent ? 'seg-item-active' : 'seg-item'"
            :title="t(`entry.intentHint.${intent}`)"
            @click="setIntent(item, intent)"
          >
            {{ t(`entry.intent.${intent}`) }}
          </button>
        </div>
        <label
          v-if="intentOf(item) === 'rate'"
          class="flex items-center gap-1 text-xs text-warm-500"
        >
          <input
            :value="rateOf(item)"
            class="input-number"
            inputmode="decimal"
            @change="setRate(item, $event.target.value)"
          />
          {{ t("entry.perMinute") }}
        </label>
      </div>
    </div>
    <button class="btn-secondary justify-center" @click="pickerOpen = true">
      <span class="i-carbon-add" /> {{ t("entry.addProduct") }}
    </button>
    <EntityPicker
      v-model:open="pickerOpen"
      kind="items"
      :candidates="makeable"
      :exclude="targets"
      :title="t('entry.pickProduct')"
      @select="add"
    />
  </div>
</template>
