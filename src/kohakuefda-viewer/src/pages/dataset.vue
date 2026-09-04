<script setup>
import { useI18n } from "@/i18n"
import { formatRate, toNumber, useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const names = useNames()
const store = useAppStore()
const tab = ref("items")
const filter = ref("")
const tabs = ["items", "machines", "recipes"]

function column(keys) {
  return keys.map((key) => ({ key, label: t(`columns.${key}`) }))
}

const columns = computed(() => ({
  machines: column(["name", "size", "belt", "pipe", "power", "modes"]),
  recipes: column(["recipe", "machine", "mode", "seconds", "inputs", "outputs", "env"]),
  items: column(["name", "phase", "id"]),
}))

function stacks(recipe, list) {
  return list
    .map((stack) => {
      const rate = (stack.count * 60) / toNumber(recipe.seconds)
      return `${stack.count} ${names.item(stack.item_id)} (${formatRate(rate)})`
    })
    .join(", ")
}

const rows = computed(() => {
  const dataset = store.dataset
  if (!dataset) {
    return { machines: [], recipes: [], items: [] }
  }
  const machines = Object.values(dataset.machines).map((machine) => {
    const belt = machine.ports.filter((p) => p.type === "belt")
    const pipe = machine.ports.filter((p) => p.type === "pipe")
    return {
      id: machine.id,
      name: names.machine(machine.id),
      size: `${machine.width}×${machine.depth}×${machine.height}`,
      belt: `${belt.filter((p) => p.direction === "in").length}/${belt.filter((p) => p.direction === "out").length}`,
      pipe: `${pipe.filter((p) => p.direction === "in").length}/${pipe.filter((p) => p.direction === "out").length}`,
      power: machine.power,
      modes: machine.modes.map((m) => m.name).join(", "),
    }
  })
  const recipes = Object.values(dataset.recipes).map((recipe) => ({
    id: recipe.id,
    machineId: recipe.machine_id,
    recipe: names.recipe(recipe.id),
    machine: names.machine(recipe.machine_id),
    mode: recipe.mode,
    seconds: recipe.seconds,
    inputs: stacks(recipe, recipe.inputs),
    outputs: stacks(recipe, recipe.outputs),
    env: recipe.env ?? "",
  }))
  const items = Object.values(dataset.items).map((item) => ({
    id: item.id,
    name: names.item(item.id),
    phase: t(`phase.${item.phase}`),
  }))
  return { machines, recipes, items }
})
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-6xl mx-auto px-4 py-4 flex flex-col gap-3">
      <h1 class="text-lg font-semibold">{{ t("dataset.heading") }}</h1>
      <p v-if="!store.dataset" class="text-secondary">{{ t(`status.${store.status}`) }}</p>
      <template v-else>
        <div class="flex items-center gap-2 flex-wrap">
          <div class="seg-group">
            <button
              v-for="name in tabs"
              :key="name"
              :class="tab === name ? 'seg-item-active' : 'seg-item'"
              @click="tab = name"
            >
              {{ t(`dataset.${name}`) }}
            </button>
          </div>
          <input v-model="filter" class="input-field w-64" :placeholder="t('dataset.filter')" />
          <span class="text-secondary">{{ t("dataset.count", { n: rows[tab].length }) }}</span>
        </div>
        <DataTable :columns="columns[tab]" :rows="rows[tab]" :filter="filter">
          <template #cell-name="{ row }">
            <EntityIcon
              :id="row.id"
              :kind="tab === 'machines' ? 'machines' : 'items'"
              :size="24"
              show-name
            />
          </template>
          <template #cell-machine="{ row }">
            <EntityIcon :id="row.machineId" kind="machines" :size="20" show-name />
          </template>
          <template #cell-id="{ row }"
            ><span class="font-mono text-warm-400">{{ row.id }}</span></template
          >
        </DataTable>
      </template>
    </div>
  </div>
</template>
