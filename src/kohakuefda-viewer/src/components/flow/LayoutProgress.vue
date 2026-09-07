<script setup>
import { useI18n } from "@/i18n"
import { frameSpace, progressOf, progressSeries } from "@/progress"

const props = defineProps({
  frame: { type: Object, default: null },
  frames: { type: Array, default: () => [] },
})
const { t } = useI18n()
const progress = computed(() => progressOf(props.frame))
const space = computed(() => frameSpace(props.frame, null))
const measure = (value) => (Number.isFinite(value) ? Number(value.toFixed(2)) : "—")
const translated = (prefix, key) =>
  t(`${prefix}.${key}`) === `${prefix}.${key}` ? key : t(`${prefix}.${key}`)
const metric = computed(() => (progress.value?.domain === "workspace" ? "target_overflow" : "area"))
const series = computed(() =>
  progressSeries(props.frames, metric.value).map((s, index) => ({
    ...s,
    label: t(`progress.${s.key}`),
    colour: index ? "#4C9989" : "#D4920A",
  })),
)
</script>

<template>
  <div v-if="progress" class="card p-2 text-xs shrink-0" role="status" data-progress>
    <div class="flex gap-x-3 gap-y-1 flex-wrap items-center">
      <strong>{{ translated("progress.phase", progress.phase) }}</strong>
      <span>{{ translated("progress", progress.display) }}</span>
      <span v-if="progress.worker !== undefined"
        >{{ t("progress.worker") }} {{ progress.worker }}</span
      >
      <span class="font-mono">{{ progress.placed ?? "—" }} / {{ progress.total ?? "—" }}</span>
      <span class="font-mono">{{ measure(progress.elapsed) }} s</span>
      <span
        >{{ t("progress.target") }} {{ space.target[2] - space.target[0] }}×{{
          space.target[3] - space.target[1]
        }}</span
      >
      <span v-if="progress.domain === 'workspace'"
        >{{ t("progress.workspace") }} {{ space.area[2] - space.area[0] }}×{{
          space.area[3] - space.area[1]
        }}</span
      >
      <span :class="progress.routed ? 'text-sage' : 'text-amber'">{{
        t(
          progress.routed
            ? "progress.targetRouted"
            : progress.workspaceRouted
              ? "progress.workspaceOnly"
              : "progress.partial",
        )
      }}</span>
      <span v-if="frame.status">{{ translated("solverUI.reason", frame.status) }}</span>
      <span v-if="frame.operator" class="font-mono"
        >{{ frame.operator }} · {{ frame.outcome }} · Δ {{ measure(frame.delta) }} · T
        {{ frame.temperature }}</span
      >
    </div>
    <div class="flex gap-x-3 gap-y-1 flex-wrap text-secondary mt-1">
      <span>{{ t("terms.area") }}: {{ measure(progress.terms.area) }}</span>
      <span
        >{{ t("terms.width") }}×{{ t("terms.height") }}: {{ measure(progress.terms.width) }}×{{
          measure(progress.terms.height)
        }}</span
      >
      <span v-if="progress.domain === 'workspace'"
        >{{ t("progress.overflow") }}: {{ measure(progress.terms.target_overflow) }} ·
        {{ t("progress.best") }}: {{ measure(progress.best?.terms?.target_overflow) }}</span
      >
      <span v-else
        >{{ t("progress.best") }} {{ t("terms.area") }}:
        {{ measure(progress.best?.terms?.area) }}</span
      >
      <span>{{ t("progress.bestMissing") }}: {{ progress.best?.missing ?? "—" }}</span>
      <span
        >{{ t("solverUI.actions") }}: {{ progress.work.actions ?? 0 }} · {{ t("solverUI.routes") }}:
        {{ progress.work.route_calls ?? 0 }}</span
      >
      <span v-if="progress.workerWork"
        >{{ t("progress.workerWork") }}: {{ progress.workerWork.actions ?? 0 }} /
        {{ progress.workerWork.route_calls ?? 0 }}</span
      >
      <span>{{ t("progress.rates") }}: {{ progress.rates }}</span>
    </div>
    <details v-if="frames.length" class="mt-1">
      <summary class="cursor-pointer">
        {{ t("progress.curve") }} · {{ t(metric === "area" ? "terms.area" : "progress.overflow") }}
      </summary>
      <CostChart :series="series" :cursor="progress.elapsed ?? -1" :height="90" :width="440" />
    </details>
  </div>
</template>
