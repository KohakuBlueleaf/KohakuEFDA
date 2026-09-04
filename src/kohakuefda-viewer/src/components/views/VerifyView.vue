<script setup>
import { ROLE_BADGE } from "@/draw"
import { useI18n } from "@/i18n"
import { formatRate, useNames } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const props = defineProps({
  highlight: { type: String, default: "" },
})
const { t } = useI18n()
const names = useNames()
const store = useAppStore()
const cellSize = ref(12)
const showGround = ref(true)
const showSky = ref(true)
const showLabels = ref(true)
const showItems = ref(true)
const showCoverage = ref(false)
const showModules = ref(Boolean(props.highlight))
const hover = ref(null)

const counts = computed(() => {
  const findings = store.report?.findings ?? []
  const count = (severity) => findings.filter((f) => f.severity === severity).length
  return { errors: count("error"), warnings: count("warning"), infos: count("info") }
})

const detail = computed(() => {
  const hit = hover.value?.hit
  if (!hit) {
    return null
  }
  const evaluation = store.evaluation
  if (hit.kind === "machine") {
    const placed = hit.entity
    const state = evaluation?.machines?.[placed.id]
    return {
      icon: { kind: "machines", id: placed.machine_id },
      title: names.machine(placed.machine_id),
      lines: [
        placed.recipe_id ? names.recipe(placed.recipe_id) : "",
        placed.config?.item ? names.item(placed.config.item) : "",
        state ? `${t("layout.utilisation")}: ${formatRate(state.utilisation)}` : "",
        state?.stalled_by ? `${t("layout.stalled")}: ${state.stalled_by}` : "",
      ].filter(Boolean),
    }
  }
  if (hit.kind === "unit") {
    return {
      icon: { kind: "logistics", id: hit.entity.unit_id },
      title: names.unit(hit.entity.unit_id),
      lines: [],
    }
  }
  if (hit.kind === "entry") {
    const entry = hit.entity
    return {
      icon: { kind: "items", id: entry.item_id },
      title: `${names.item(entry.item_id)} · ${t("legend.entry")}`,
      lines: [`${formatRate(entry.rate)}/min`, `${t("layout.fromEdge")} ${entry.edge}`],
    }
  }
  const segment = hit.entity
  const flow = evaluation?.segments?.[segment.id]
  const lines = flow
    ? Object.entries(flow.items).map(
        ([item, rate]) => `${names.item(item)} ${formatRate(rate)}/min`,
      )
    : segment.item_id
      ? [names.item(segment.item_id)]
      : []
  const title = segment.item_id
    ? `${names.item(segment.item_id)} · ${t(`graph.${segment.kind}`)}`
    : `${segment.id} · ${t(`graph.${segment.kind}`)}`
  return { icon: segment.item_id ? { kind: "items", id: segment.item_id } : null, title, lines }
})
</script>

<template>
  <div v-if="!store.layout" class="card p-8 text-center text-secondary">
    {{ t("verify.noLayout") }}
  </div>
  <div v-else class="flex flex-col gap-2">
    <div class="flex items-center gap-2 flex-wrap text-xs">
      <span v-if="store.report" :class="counts.errors ? 'chip-coral' : 'chip-aqua'">
        <span :class="counts.errors ? 'i-carbon-warning-alt' : 'i-carbon-checkmark'" />
        {{ counts.errors ? t("verify.errors", { n: counts.errors }) : t("verify.ok") }}
      </span>
      <span v-if="counts.warnings" class="chip-amber">{{
        t("verify.warnings", { n: counts.warnings })
      }}</span>
      <span v-if="counts.infos" class="chip-sapphire">{{
        t("verify.notes", { n: counts.infos })
      }}</span>
      <span class="flex-1" />
      <label class="flex items-center gap-1"
        ><input v-model="showGround" type="checkbox" class="accent-iolite" />
        {{ t("layout.ground") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showSky" type="checkbox" class="accent-iolite" />
        {{ t("layout.sky") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showLabels" type="checkbox" class="accent-iolite" />
        {{ t("layout.labels") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showItems" type="checkbox" class="accent-iolite" />
        {{ t("layout.items") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showModules" type="checkbox" class="accent-iolite" />
        {{ t("layout.modules") }}</label
      >
      <label class="flex items-center gap-1"
        ><input v-model="showCoverage" type="checkbox" class="accent-iolite" />
        {{ t("layout.coverage") }}</label
      >
      <label class="flex items-center gap-1"
        >{{ t("layout.cell") }}
        <input v-model.number="cellSize" type="range" min="4" max="28" class="accent-iolite"
      /></label>
    </div>
    <LayoutCanvas
      v-if="store.dataset"
      :layout="store.layout"
      :dataset="store.dataset"
      :cell-size="cellSize"
      :show-ground="showGround"
      :show-sky="showSky"
      :show-labels="showLabels"
      :show-items="showItems"
      :show-modules="showModules"
      :show-coverage="showCoverage"
      :highlight="highlight"
      :lang="names.lang.value"
      @hover="hover = $event"
    />
    <div class="flex items-center gap-3 flex-wrap text-xs min-h-6">
      <template v-if="detail">
        <EntityIcon v-if="detail.icon" :id="detail.icon.id" :kind="detail.icon.kind" :size="20" />
        <strong>{{ detail.title }}</strong>
        <span v-for="line in detail.lines" :key="line" class="text-secondary">{{ line }}</span>
      </template>
      <span v-else class="text-secondary">{{
        hover ? `(${hover.x}, ${hover.y})` : t("layout.hover")
      }}</span>
    </div>
    <div class="flex items-center gap-3 flex-wrap text-[10px] text-warm-500">
      <span v-for="(badge, role) in ROLE_BADGE" :key="role" class="flex items-center gap-1">
        <span class="font-bold font-mono px-1 rounded bg-warm-100 dark:bg-warm-800">{{
          badge.glyph
        }}</span>
        {{ t(`legend.${badge.key}`) }}
      </span>
      <span class="flex-1" />
      <RouterLink to="/layout" class="text-iolite">{{ t("nav.layout") }} →</RouterLink>
      <RouterLink to="/modules" class="text-iolite">{{ t("nav.modules") }} →</RouterLink>
      <RouterLink to="/report" class="text-iolite">{{ t("nav.report") }} →</RouterLink>
    </div>
  </div>
</template>
