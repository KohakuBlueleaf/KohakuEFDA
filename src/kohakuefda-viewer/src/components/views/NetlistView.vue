<script setup>
import { useI18n } from "@/i18n"
import { formatRate, useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const names = useNames()
const store = useAppStore()
const netlist = computed(() => store.netlist)

const columns = computed(() =>
  ["item", "from", "to", "rate", "lanes"].map((key) => ({ key, label: t(`columns.${key}`) })),
)
const nets = computed(() =>
  (netlist.value?.nets ?? []).map((net) => ({
    id: net.id,
    itemId: net.item_id,
    item: names.item(net.item_id),
    from: net.sources.map((s) => s.cell_id).join(", "),
    to: net.sinks.map((s) => s.cell_id).join(", "),
    rate: formatRate(net.rate),
    lanes: `${net.trunk_lanes} ${net.kind}`,
  })),
)

function title(cell) {
  if (cell.recipe_id) {
    return names.recipe(cell.recipe_id)
  }
  return t(`cellKind.${cell.kind}`)
}
</script>

<template>
  <div v-if="!netlist" class="card p-8 text-center text-secondary">{{ t("netlist.none") }}</div>
  <div v-else class="flex flex-col gap-4">
    <div class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))">
      <div v-for="cell in netlist.cells" :key="cell.id" class="card p-3 flex flex-col gap-2">
        <div class="flex items-center gap-2">
          <EntityIcon :id="cell.machine_id" kind="machines" :size="32" />
          <div class="min-w-0 flex-1">
            <div class="text-xs font-medium truncate">{{ title(cell) }}</div>
            <div class="text-[10px] text-warm-500">
              {{ names.machine(cell.machine_id) }} · {{ cell.width }}×{{ cell.height }}
              <span v-if="cell.group" class="chip-warm ml-1">{{ cell.group }}</span>
            </div>
          </div>
          <span class="chip-warm font-mono">{{ cell.id }}</span>
        </div>
        <FragmentCanvas
          v-if="store.dataset"
          :fragment="cell"
          :dataset="store.dataset"
          :lang="names.lang.value"
        />
        <div class="flex flex-wrap gap-1">
          <span
            v-for="pin in cell.pins"
            :key="pin.id"
            :class="pin.direction === 'in' ? 'chip-aqua' : 'chip-coral'"
            :title="`${pin.id} ${pin.edge}`"
          >
            <span
              :class="pin.direction === 'in' ? 'i-carbon-arrow-down' : 'i-carbon-arrow-up'"
              class="text-[9px]"
            />
            <EntityIcon :id="pin.item_id" kind="items" :size="14" />
            {{ formatRate(pin.rate) }}
          </span>
        </div>
      </div>
    </div>
    <h4 class="section-title">{{ t("netlist.nets") }}</h4>
    <DataTable :columns="columns" :rows="nets">
      <template #cell-item="{ row }"
        ><EntityIcon :id="row.itemId" kind="items" :size="20" show-name
      /></template>
    </DataTable>
  </div>
</template>
