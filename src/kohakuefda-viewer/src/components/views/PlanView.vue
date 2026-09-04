<script setup>
import { useI18n } from "@/i18n"
import { formatRate, useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const names = useNames()
const store = useAppStore()
const plan = computed(() => store.plan)
const STATUS_TONE = { ok: "text-aquamarine", degraded: "text-amber", infeasible: "text-coral" }

const areaUsed = computed(() => {
  const square = store.square
  if (!plan.value || !square) {
    return ""
  }
  return `${Math.round((100 * plan.value.footprint_cells) / (square[0] * square[1]))}%`
})

function column(keys) {
  return keys.map((key) => ({ key, label: t(`columns.${key}`) }))
}

const targets = computed(() =>
  (plan.value?.targets ?? []).map((target) => ({
    id: target.item_id,
    item: names.item(target.item_id),
    goal: target.goal ?? "rate",
    requested: formatRate(target.requested),
    achieved: formatRate(target.achieved),
    tone: target.achieved < target.requested ? "warning" : "",
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
const blockers = computed(() => (plan.value?.findings ?? []).filter((f) => f.severity === "error"))
const alternatives = computed(() => store.alternatives?.alternatives ?? [])
const bannable = computed(() => store.alternatives?.bannable ?? [])

function compare(alternative) {
  const current = plan.value
  if (!current) {
    return ""
  }
  const machines = alternative.machine_count - current.machine_count
  const cells = alternative.footprint_cells - current.footprint_cells
  const sign = (n) => (n > 0 ? `+${n}` : `${n}`)
  return t("plan.alternativeDelta", { machines: sign(machines), cells: sign(cells) })
}
</script>

<template>
  <div v-if="!plan" class="card p-8 text-center text-secondary">{{ t("outcomes.noPlan") }}</div>
  <div v-else class="flex flex-col gap-4">
    <div v-if="blockers.length" class="card p-3 flex flex-col gap-1.5 border-coral">
      <span class="text-xs font-medium text-coral">
        <span class="i-carbon-warning-alt" /> {{ t("plan.cannotBuild") }}
      </span>
      <div v-for="(finding, n) in blockers" :key="n" class="flex items-center gap-2 text-xs">
        <EntityIcon
          v-if="store.dataset?.items?.[finding.subject]"
          :id="finding.subject"
          kind="items"
          :size="18"
          show-name
        />
        <span class="text-secondary">{{ finding.message }}</span>
      </div>
      <span class="text-[10px] text-secondary">{{ t("plan.cannotBuildHint") }}</span>
    </div>
    <div class="card p-3 flex flex-wrap gap-6">
      <Metric
        :label="t('plan.status')"
        :value="t(`planStatus.${plan.status}`)"
        :tone="STATUS_TONE[plan.status]"
      />
      <Metric :label="t('plan.machineCount')" :value="plan.machine_count" />
      <Metric :label="t('plan.power')" :value="plan.power" :hint="t('plan.powerDraw')" />
      <Metric
        :label="t('plan.footprint')"
        :value="plan.footprint_cells"
        :hint="areaUsed ? t('plan.areaUsed', { pct: areaUsed }) : ''"
      />
      <Metric :label="t('plan.scale')" :value="formatRate(plan.scale)" />
    </div>
    <OutcomesBoard />
    <details class="card" open>
      <summary class="px-3 py-2 text-xs font-medium cursor-pointer">{{ t("plan.graph") }}</summary>
      <div class="p-2"><PlanGraph :plan="plan" /></div>
    </details>
    <details class="card" :open="alternatives.length > 0">
      <summary class="px-3 py-2 text-xs font-medium cursor-pointer">
        {{ t("plan.alternatives") }}
        <span class="chip-warm ml-1">{{ alternatives.length }}</span>
      </summary>
      <div class="p-3 flex flex-col gap-3 text-xs">
        <p class="text-secondary">{{ t("plan.alternativesHint") }}</p>
        <p v-if="!alternatives.length" class="text-secondary">{{ t("plan.noAlternatives") }}</p>
        <div
          v-for="alternative in alternatives"
          :key="alternative.recipe_id"
          class="flex items-center gap-3 flex-wrap"
        >
          <EntityIcon :id="alternative.item_id" kind="items" :size="22" show-name />
          <span class="text-secondary">{{ t("plan.via") }}</span>
          <EntityIcon :id="alternative.machine_id" kind="machines" :size="22" show-name />
          <span class="chip-warm">{{ names.recipe(alternative.recipe_id) }}</span>
          <span :class="alternative.status === 'ok' ? 'chip-aqua' : 'chip-amber'">
            {{ alternative.machine_count }} {{ t("plan.machinesShort") }} ·
            {{ alternative.footprint_cells }} {{ t("plan.cellsShort") }} ·
            {{ compare(alternative) }}
          </span>
          <button
            class="btn-secondary !text-xs"
            :disabled="store.runBusy"
            @click="store.useAlternative(alternative)"
          >
            <span class="i-carbon-arrow-right" /> {{ t("plan.usePath") }}
          </button>
        </div>
        <template v-if="bannable.length">
          <span class="section-title">{{ t("plan.bannable") }}</span>
          <p class="text-secondary">{{ t("plan.bannableHint") }}</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="machine in bannable"
              :key="machine"
              class="chip-coral !py-1"
              :disabled="store.runBusy"
              :title="t('plan.banAndRebuild')"
              @click="store.banAndRebuild(machine)"
            >
              <span class="i-carbon-close text-[10px]" />
              <EntityIcon :id="machine" kind="machines" :size="18" show-name />
            </button>
          </div>
        </template>
      </div>
    </details>
    <details class="card">
      <summary class="px-3 py-2 text-xs font-medium cursor-pointer">
        {{ t("plan.details") }}
      </summary>
      <div class="p-3 flex flex-col gap-3">
        <h4 class="section-title">{{ t("plan.targets") }}</h4>
        <DataTable :columns="column(['item', 'goal', 'requested', 'achieved'])" :rows="targets">
          <template #cell-item="{ row }"
            ><EntityIcon :id="row.id" kind="items" :size="20" show-name
          /></template>
          <template #cell-goal="{ row }"
            ><span class="chip-warm">{{ t(`entry.intent.${row.goal}`) }}</span></template
          >
        </DataTable>
        <h4 class="section-title">{{ t("plan.recipes") }}</h4>
        <DataTable
          :columns="column(['recipe', 'machine', 'mode', 'crafts', 'machines'])"
          :rows="recipes"
        >
          <template #cell-machine="{ row }"
            ><EntityIcon :id="row.machineId" kind="machines" :size="20" show-name
          /></template>
        </DataTable>
        <h4 class="section-title">{{ t("plan.findings") }}</h4>
        <FindingsTable :findings="plan.findings" />
        <RouterLink to="/plan" class="text-iolite text-xs">{{ t("plan.openFull") }} →</RouterLink>
      </div>
    </details>
  </div>
</template>
