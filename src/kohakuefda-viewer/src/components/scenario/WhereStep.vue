<script setup>
import { useI18n } from "@/i18n"
import { pickName } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()

const basement = computed(() => store.scenario.basement)
const areas = computed(() =>
  (store.meta?.basements ?? []).filter((b) => b.region === basement.value.region),
)
const area = computed(() => areas.value.find((b) => b.id === basement.value.basement_id))
const levels = computed(() => Object.entries(area.value?.square_by_level ?? {}))
const depotLevels = computed(() => area.value?.depot_levels ?? [1])

function setRegion(region) {
  basement.value.region = region
  if (!areas.value.some((b) => b.id === basement.value.basement_id)) {
    basement.value.basement_id = areas.value[0]?.id ?? ""
  }
  store.refreshRequirements()
}

function areaLabel(entry) {
  return pickName(entry.names, store.lang) || entry.id
}

function levelLabel([level, square]) {
  return square ? `L${level} · ${square[0]}×${square[1]}` : `L${level} · ?`
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="seg-group w-full">
      <button
        v-for="region in store.meta?.regions ?? []"
        :key="region"
        class="flex-1 text-center"
        :class="basement.region === region ? 'seg-item-active' : 'seg-item'"
        @click="setRegion(region)"
      >
        {{ t(`region.${region}`) }}
      </button>
    </div>
    <label class="flex flex-col gap-0.5">
      <span class="section-title">{{ t("entry.area") }}</span>
      <select v-model="basement.basement_id" class="select-field">
        <option v-for="entry in areas" :key="entry.id" :value="entry.id">
          {{ areaLabel(entry) }}{{ entry.hub ? ` · ${t("entry.hub")}` : "" }}
        </option>
      </select>
    </label>
    <div class="grid grid-cols-2 gap-2">
      <label class="flex flex-col gap-0.5">
        <span class="section-title">{{ t("entry.level") }}</span>
        <select v-model.number="basement.level" class="select-field">
          <option v-for="entry in levels" :key="entry[0]" :value="Number(entry[0])">
            {{ levelLabel(entry) }}
          </option>
        </select>
      </label>
      <label class="flex flex-col gap-0.5">
        <span class="section-title">{{ t("entry.depotLevel") }}</span>
        <select v-model.number="basement.depot_level" class="select-field">
          <option v-for="level in depotLevels" :key="level" :value="level">L{{ level }}</option>
        </select>
      </label>
    </div>
    <p class="text-secondary">
      {{
        store.square
          ? t("entry.square", { w: store.square[0], h: store.square[1] })
          : t("entry.squareUnknown")
      }}
    </p>
  </div>
</template>
