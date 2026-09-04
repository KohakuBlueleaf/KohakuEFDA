<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const pickerOpen = ref(false)
const showIntermediates = ref(false)

const rows = computed(() =>
  Object.keys(store.scenario.supply)
    .filter((item) => !store.requirements.gathered.includes(item))
    .sort(),
)
const natural = computed(() => new Set(store.requirements.natural))
const gathered = computed(() => store.requirements.gathered)
const intermediates = computed(() =>
  store.requirements.intermediates.filter((item) => !(item in store.scenario.supply)),
)

function source(item) {
  const kind = store.dataset?.resources?.[item]
  if (kind === "mine") {
    return "entry.mined"
  }
  if (kind) {
    return "entry.pumped"
  }
  return (store.dataset?.items?.[item]?.phase ?? 1) === 1 ? "entry.fromDepot" : "entry.fromOutside"
}

function valueOf(item) {
  const value = store.scenario.supply[item]
  return value === null || value === undefined ? "" : String(value)
}

function setValue(item, value) {
  store.scenario.supply[item] = value.trim() === "" ? null : value.trim()
}

function add(item) {
  store.scenario.supply[item] = null
}

function toggleGathered(item, on) {
  if (on) {
    store.scenario.supply[item] = null
  } else {
    delete store.scenario.supply[item]
  }
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <p v-if="!rows.length" class="text-secondary">{{ t("entry.noNeeds") }}</p>
    <div v-for="item in rows" :key="item" class="card p-2 flex items-center gap-2">
      <EntityIcon
        :id="item"
        kind="items"
        :size="32"
        show-name
        class="flex-1 min-w-0 text-xs font-medium"
      />
      <span :class="natural.has(item) ? 'chip-sage' : 'chip-warm'">{{ t(source(item)) }}</span>
      <input
        :value="valueOf(item)"
        class="input-number"
        inputmode="decimal"
        :placeholder="t('entry.plenty')"
        :title="t('entry.perMinute')"
        @change="setValue(item, $event.target.value)"
      />
      <button
        class="btn-icon !w-6 !h-6"
        :title="natural.has(item) ? t('entry.dropped') : t('entry.remove')"
        @click="store.dropSupply(item)"
      >
        <span class="i-carbon-close text-[11px]" />
      </button>
    </div>
    <p class="text-secondary">{{ t("entry.haveHint") }}</p>
    <div v-if="gathered.length" class="card p-2 flex flex-col gap-1.5 border-amber/40">
      <span class="text-[11px] font-medium text-amber-shadow dark:text-amber">
        {{ t("entry.gathered") }}
      </span>
      <p class="text-[10px] text-warm-500">{{ t("entry.gatheredHint") }}</p>
      <label v-for="item in gathered" :key="item" class="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          class="accent-iolite"
          :checked="item in store.scenario.supply"
          @change="toggleGathered(item, $event.target.checked)"
        />
        <EntityIcon :id="item" kind="items" :size="22" show-name class="flex-1 min-w-0" />
        <input
          v-if="item in store.scenario.supply"
          :value="valueOf(item)"
          class="input-number"
          inputmode="decimal"
          :placeholder="t('entry.plenty')"
          @change="setValue(item, $event.target.value)"
        />
      </label>
    </div>
    <div v-if="intermediates.length" class="flex flex-col gap-1">
      <button class="btn-ghost self-start" @click="showIntermediates = !showIntermediates">
        <span :class="showIntermediates ? 'i-carbon-chevron-down' : 'i-carbon-chevron-right'" />
        {{ t("entry.alreadyHave") }}
      </button>
      <div v-if="showIntermediates" class="flex flex-wrap gap-1">
        <button
          v-for="item in intermediates"
          :key="item"
          class="btn-secondary !py-0.5 !px-1.5 !text-[11px]"
          @click="add(item)"
        >
          <EntityIcon :id="item" kind="items" :size="18" show-name />
        </button>
      </div>
    </div>
    <button class="btn-secondary justify-center" @click="pickerOpen = true">
      <span class="i-carbon-add" /> {{ t("entry.addMaterial") }}
    </button>
    <EntityPicker
      v-model:open="pickerOpen"
      kind="items"
      :candidates="store.factoryItems"
      :exclude="rows"
      :title="t('entry.pickMaterial')"
      @select="add"
    />
  </div>
</template>
