<script setup>
import { useI18n } from "@/i18n"
import { useNames } from "@/i18n/names"
import { productionMachines } from "@/rules"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const names = useNames()
const store = useAppStore()
const advanced = ref(false)
const pickerOpen = ref(false)
const banPickerOpen = ref(false)

const scenario = computed(() => store.scenario)
const overrides = computed(() => Object.entries(scenario.value.recipe_overrides ?? {}))
const banned = computed(() => scenario.value.banned_machines ?? [])

function recipesFor(item) {
  return Object.values(store.dataset?.recipes ?? {}).filter((recipe) =>
    recipe.outputs.some((stack) => stack.item_id === item),
  )
}

function setOverride(item, recipe) {
  if (recipe) {
    scenario.value.recipe_overrides[item] = recipe
  } else {
    delete scenario.value.recipe_overrides[item]
  }
}

function addOverride(item) {
  const first = recipesFor(item)[0]
  scenario.value.recipe_overrides[item] = first ? first.id : ""
}

function ban(machine) {
  if (!banned.value.includes(machine)) {
    scenario.value.banned_machines = [...banned.value, machine]
    store.refreshRequirements()
  }
}

function unban(machine) {
  scenario.value.banned_machines = banned.value.filter((m) => m !== machine)
  store.refreshRequirements()
}

function setAreaFill(value) {
  scenario.value.area_fill = value === "" ? null : Number(value)
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="grid grid-cols-2 gap-2">
      <button
        class="card-hover p-2 text-left"
        :class="scenario.mode === 'machines' ? 'border-iolite ring-1 ring-iolite/30' : ''"
        @click="scenario.mode = 'machines'"
      >
        <span class="i-carbon-minimize text-iolite" />
        <div class="text-xs font-medium mt-1">{{ t("entry.simplest") }}</div>
        <div class="text-[10px] text-warm-500">{{ t("entry.simplestHint") }}</div>
      </button>
      <button
        class="card-hover p-2 text-left"
        :class="scenario.mode === 'area' ? 'border-iolite ring-1 ring-iolite/30' : ''"
        @click="scenario.mode = 'area'"
      >
        <span class="i-carbon-maximize text-iolite" />
        <div class="text-xs font-medium mt-1">{{ t("entry.efficient") }}</div>
        <div class="text-[10px] text-warm-500">{{ t("entry.efficientHint") }}</div>
      </button>
    </div>
    <div class="flex flex-col gap-1.5 text-xs">
      <label class="flex items-center gap-2" :title="t('entry.liquidsHint')">
        <input
          v-model="scenario.liquids"
          type="checkbox"
          class="accent-iolite"
          @change="store.refreshRequirements()"
        />
        {{ t("entry.liquids") }}
      </label>
      <label class="flex items-center gap-2" :title="t('entry.gasHint')">
        <input
          v-model="scenario.gas"
          type="checkbox"
          class="accent-iolite"
          @change="store.refreshRequirements()"
        />
        {{ t("entry.gas") }}
      </label>
      <span class="section-title mt-1">{{ t("entry.banned") }}</span>
      <p class="text-[10px] text-warm-500">{{ t("entry.bannedHint") }}</p>
      <div class="flex flex-wrap gap-1">
        <span v-for="machine in banned" :key="machine" class="chip-coral !py-1">
          <EntityIcon :id="machine" kind="machines" :size="18" show-name />
          <button class="ml-1" :title="t('entry.remove')" @click="unban(machine)">
            <span class="i-carbon-close text-[10px]" />
          </button>
        </span>
        <button class="btn-secondary !py-0.5 !px-1.5 !text-[11px]" @click="banPickerOpen = true">
          <span class="i-carbon-add" /> {{ t("entry.banMachine") }}
        </button>
      </div>
    </div>
    <button class="btn-ghost self-start" @click="advanced = !advanced">
      <span :class="advanced ? 'i-carbon-chevron-down' : 'i-carbon-chevron-right'" />
      {{ t("entry.advanced") }}
    </button>
    <div v-if="advanced" class="flex flex-col gap-2 text-xs">
      <label class="flex items-center gap-2">
        <input v-model="scenario.mode" type="radio" value="balanced" class="accent-iolite" />
        {{ t("entry.balanced") }}
      </label>
      <label class="flex items-center gap-2" :title="t('entry.mixedLanesHint')">
        <input v-model="scenario.mixed_lanes" type="checkbox" class="accent-iolite" />
        {{ t("entry.mixedLanes") }}
      </label>
      <label class="flex items-center justify-between gap-2" :title="t('entry.areaFillHint')">
        <span>{{ t("entry.areaFill") }}</span>
        <input
          type="number"
          min="0.05"
          max="1"
          step="0.05"
          class="input-number"
          :value="scenario.area_fill ?? ''"
          placeholder="0.5"
          @change="setAreaFill($event.target.value)"
        />
      </label>
      <span class="section-title">{{ t("entry.overrides") }}</span>
      <div v-for="[item, recipe] in overrides" :key="item" class="flex items-center gap-2">
        <EntityIcon :id="item" kind="items" :size="22" show-name class="flex-1 min-w-0" />
        <select
          class="select-field !py-0.5 !text-[11px] max-w-48"
          :value="recipe"
          @change="setOverride(item, $event.target.value)"
        >
          <option v-for="option in recipesFor(item)" :key="option.id" :value="option.id">
            {{ names.recipe(option.id) }} · {{ names.machine(option.machine_id) }}
          </option>
        </select>
        <button class="btn-icon !w-6 !h-6" @click="setOverride(item, '')">
          <span class="i-carbon-close text-[11px]" />
        </button>
      </div>
      <button class="btn-secondary !text-xs self-start" @click="pickerOpen = true">
        <span class="i-carbon-add" /> {{ t("entry.addOverride") }}
      </button>
      <EntityPicker
        v-model:open="pickerOpen"
        kind="items"
        :candidates="store.factoryItems.filter((id) => recipesFor(id).length > 1)"
        :exclude="overrides.map(([item]) => item)"
        :title="t('entry.pickOverride')"
        @select="addOverride"
      />
    </div>
    <EntityPicker
      v-model:open="banPickerOpen"
      kind="machines"
      :candidates="productionMachines(store.dataset)"
      :exclude="banned"
      :title="t('entry.pickBan')"
      @select="ban"
    />
  </div>
</template>
