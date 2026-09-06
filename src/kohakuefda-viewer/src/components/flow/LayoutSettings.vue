<script setup>
import { useI18n } from "@/i18n"
import {
  PRIMARY,
  collectLayout,
  effectiveLimits,
  fieldGroups,
  layoutFields,
  optionValues,
  parseOptions,
  solverEntry,
} from "@/layout-settings"
import { useAppStore } from "@/stores/app"

const store = useAppStore()
const { t } = useI18n()
const draft = computed(() => store.draftParams("layout"))
const entry = computed(() => solverEntry(store.solvers, draft.value.solver))
const fields = computed(() =>
  layoutFields(store.params.layout ?? {}, store.solvers, draft.value.solver),
)
const primary = computed(() =>
  PRIMARY.map((key) => fields.value.find((f) => f.key === key)).filter(Boolean),
)
const groups = computed(() => fieldGroups(fields.value))
const checked = computed(() => {
  try {
    return {
      payload: collectLayout(store.params.layout ?? {}, store.solvers, draft.value),
      error: "",
    }
  } catch (error) {
    return { payload: null, error: String(error.message) }
  }
})
const jsonInvalid = computed(() => {
  try {
    parseOptions(draft.value.solver_options)
    return false
  } catch {
    return true
  }
})
const limits = computed(() =>
  checked.value.payload ? effectiveLimits(checked.value.payload) : null,
)
const choices = computed(() => ({
  solver: store.solvers.map((e) => e.name),
  backend: ["auto", "python", "native"],
  entry_sides: ["NW", "N", "W", "NESW"],
  flow_order: ["bottom-up", "top-down"],
}))
function value(field) {
  if (field.scope === "stage") return draft.value[field.key] ?? field.default
  try {
    return optionValues(entry.value, draft.value)[field.key]
  } catch {
    return field.default
  }
}
function update(field, value) {
  if (field.key === "solver") {
    store.switchDraftSolver(value)
    return
  }
  if (field.scope === "stage") {
    draft.value[field.key] = value
    return
  }
  const options = parseOptions(draft.value.solver_options)
  options[field.key] = value
  draft.value.solver_options = JSON.stringify(options)
}
function preset(seconds) {
  draft.value.seconds = seconds
  draft.value.max_actions = 0
  if (entry.value && "until_budget" in entry.value.defaults) {
    update({ key: "until_budget", scope: "solver" }, true)
  }
}
</script>

<template>
  <div class="flex flex-col gap-2 text-xs">
    <div class="flex items-center gap-2">
      <span class="section-title">{{ t("flow.params") }}</span>
      <span class="flex-1" />
      <button class="btn-secondary !text-[10px] !py-0.5" @click="store.resetDraft('layout')">
        {{ t("flow.reset") }}
      </button>
    </div>
    <p v-if="!entry" class="text-coral">{{ t("solverUI.catalogMissing") }}</p>
    <SettingField
      v-for="field in primary"
      :key="`${field.scope}:${field.key}`"
      :field="field"
      :value="value(field)"
      :choices="choices[field.key] ?? []"
      :disabled="jsonInvalid && field.scope === 'solver'"
      @change="update(field, $event)"
    />
    <div class="flex items-center gap-1 flex-wrap">
      <span class="text-secondary">{{ t("solverUI.timePresets") }}</span>
      <button
        v-for="seconds in [60, 300, 600]"
        :key="seconds"
        class="btn-secondary !text-[10px] !py-0.5"
        :disabled="jsonInvalid"
        @click="preset(seconds)"
      >
        {{ seconds }} s
      </button>
    </div>
    <p class="text-secondary">{{ t("solverUI.presetsHint") }}</p>
    <div
      v-if="limits"
      class="rounded bg-warm-100 dark:bg-warm-800 p-2 flex flex-col gap-1"
      role="status"
    >
      <strong>{{ t("solverUI.effectiveLimits") }}</strong>
      <span>{{ t("solverUI.firstLimit") }}</span>
      <span v-if="limits.untilBudget">{{ t("solverUI.budgetDriven") }}</span>
      <span v-else-if="'until_budget' in limits.options" class="text-amber">{{
        t(limits.global ? "solverUI.stepDriven" : "solverUI.noGlobalBudget")
      }}</span>
      <span v-if="limits.options.construction_steps === 0" class="text-amber">{{
        t("solverUI.constructionSkipped")
      }}</span>
      <span v-if="limits.options.improvement_steps === 0">{{
        t("solverUI.improvementSkipped")
      }}</span>
      <span v-if="!entry.parallel">{{ t("solverUI.serial") }}</span>
      <span v-if="draft.solver === 'hc'">{{ t("solverUI.hcTemperatures") }}</span>
    </div>
    <details v-for="group in groups" :key="group.key">
      <summary class="section-title cursor-pointer">{{ t(`paramGroup.${group.key}`) }}</summary>
      <div class="flex flex-col gap-1.5 mt-2">
        <SettingField
          v-for="field in group.fields"
          :key="`${field.scope}:${field.key}`"
          :field="field"
          :value="value(field)"
          :choices="choices[field.key] ?? []"
          :disabled="jsonInvalid && field.scope === 'solver'"
          @change="update(field, $event)"
        />
      </div>
    </details>
    <details>
      <summary class="section-title cursor-pointer">{{ t("params.solver_options") }}</summary>
      <p class="text-secondary my-1">{{ t("solverUI.jsonHint") }}</p>
      <textarea
        v-model="draft.solver_options"
        class="w-full input-number !text-left font-mono"
        rows="5"
        aria-label="Solver options JSON"
      />
    </details>
    <p v-if="checked.error" class="text-coral break-words" role="alert">{{ checked.error }}</p>
  </div>
</template>
