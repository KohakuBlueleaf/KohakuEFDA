<script setup>
import { useI18n } from "@/i18n"
import { formatRate, useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const names = useNames()
const store = useAppStore()
const plan = computed(() => store.plan)

function column(keys) {
  return keys.map((key) => ({ key, label: t(`columns.${key}`) }))
}

function endpoint(name) {
  return store.dataset?.recipes?.[name] ? names.recipe(name) : t(`endpoint.${name}`)
}

const targets = computed(() =>
  (plan.value?.targets ?? []).map((target) => ({
    id: target.item_id,
    item: names.item(target.item_id),
    goal: target.goal ?? "rate",
    requested: formatRate(target.requested),
    achieved: formatRate(target.achieved),
  })),
)
const recipes = computed(() =>
  (plan.value?.recipes ?? []).map((use) => ({
    id: use.recipe_id,
    machineId: use.machine_id,
    recipe: names.recipe(use.recipe_id),
    machine: names.machine(use.machine_id),
    mode: use.mode,
    crafts: formatRate(use.crafts_per_min),
    machines: `${use.machines} (${formatRate(use.machines_exact)})`,
  })),
)
const items = computed(() =>
  Object.values(plan.value?.items ?? {}).map((balance) => ({
    id: balance.item_id,
    item: names.item(balance.item_id),
    produced: formatRate(balance.produced),
    consumed: formatRate(balance.consumed),
    supplied: formatRate(balance.supplied),
    delivered: formatRate(balance.delivered),
    sunk: balance.sink_kind
      ? `${formatRate(balance.sunk)} → ${t(`endpoint.${balance.sink_kind}`)}`
      : "0",
    net: formatRate(balance.net),
  })),
)
const nets = computed(() =>
  (plan.value?.nets ?? []).map((net, index) => ({
    id: index,
    itemId: net.item_id,
    item: names.item(net.item_id),
    from: endpoint(net.source),
    to: endpoint(net.target),
    rate: formatRate(net.rate),
    lanes: `${net.lanes} ${net.fluid ? t("graph.pipe") : t("graph.belt")}`,
  })),
)
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-6xl mx-auto px-4 py-4 flex flex-col gap-3">
      <h1 class="text-lg font-semibold">{{ t("plan.heading") }}</h1>
      <p v-if="!plan" class="card p-8 text-center text-secondary">{{ t("status.missing") }}</p>
      <template v-else>
        <div class="card p-3 flex flex-wrap gap-6">
          <Metric :label="t('plan.status')" :value="t(`planStatus.${plan.status}`)" />
          <Metric :label="t('plan.scale')" :value="formatRate(plan.scale)" />
          <Metric :label="t('plan.machineCount')" :value="plan.machine_count" />
          <Metric :label="t('plan.power')" :value="plan.power" />
          <Metric :label="t('plan.footprint')" :value="plan.footprint_cells" />
        </div>
        <h2 class="section-title">{{ t("plan.graph") }}</h2>
        <PlanGraph :plan="plan" />
        <h2 class="section-title">{{ t("plan.targets") }}</h2>
        <DataTable :columns="column(['item', 'goal', 'requested', 'achieved'])" :rows="targets">
          <template #cell-item="{ row }"
            ><EntityIcon :id="row.id" kind="items" :size="20" show-name
          /></template>
          <template #cell-goal="{ row }"
            ><span class="chip-warm">{{ t(`entry.intent.${row.goal}`) }}</span></template
          >
        </DataTable>
        <h2 class="section-title">{{ t("plan.recipes") }}</h2>
        <DataTable
          :columns="column(['recipe', 'machine', 'mode', 'crafts', 'machines'])"
          :rows="recipes"
        >
          <template #cell-machine="{ row }"
            ><EntityIcon :id="row.machineId" kind="machines" :size="20" show-name
          /></template>
        </DataTable>
        <h2 class="section-title">{{ t("plan.items") }}</h2>
        <DataTable
          :columns="
            column(['item', 'produced', 'consumed', 'supplied', 'delivered', 'sunk', 'net'])
          "
          :rows="items"
        >
          <template #cell-item="{ row }"
            ><EntityIcon :id="row.id" kind="items" :size="20" show-name
          /></template>
        </DataTable>
        <h2 class="section-title">{{ t("plan.nets") }}</h2>
        <DataTable :columns="column(['item', 'from', 'to', 'rate', 'lanes'])" :rows="nets">
          <template #cell-item="{ row }"
            ><EntityIcon :id="row.itemId" kind="items" :size="20" show-name
          /></template>
        </DataTable>
        <h2 class="section-title">{{ t("plan.findings") }}</h2>
        <FindingsTable :findings="plan.findings" />
      </template>
    </div>
  </div>
</template>
