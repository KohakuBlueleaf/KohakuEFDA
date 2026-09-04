<script setup>
import { useI18n } from "@/i18n"
import { pickName } from "@/i18n/names"
import { STAGES, useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const router = useRouter()

onMounted(() => {
  if (store.apiAvailable) {
    store.listRuns()
  }
})

async function open(runId) {
  await store.openRun(runId)
  router.push("/")
}

function remove(run) {
  if (window.confirm(t("runs.confirmDelete", { id: run.id }))) {
    store.deleteRun(run.id)
  }
}

function when(time) {
  return new Date(time * 1000).toLocaleString()
}

function areaName(run) {
  const entry = store.meta?.basements?.find((b) => b.id === run.scenario.basement.basement_id)
  return entry ? pickName(entry.names, store.lang) : run.scenario.basement.basement_id
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-5xl mx-auto px-4 py-4 flex flex-col gap-3">
      <div>
        <h1 class="text-lg font-semibold">{{ t("runs.heading") }}</h1>
        <p class="text-secondary">{{ t("runs.intro") }}</p>
      </div>
      <p v-if="!store.apiAvailable" class="card p-6 text-center text-coral text-xs">
        {{ t("flow.noApi") }}
      </p>
      <p v-else-if="!store.runs.length" class="card p-8 text-center text-secondary">
        {{ t("runs.none") }}
      </p>
      <div
        v-for="run in store.runs"
        :key="run.id"
        class="card-hover p-3 flex flex-col sm:flex-row sm:items-center gap-3"
        :class="run.id === store.run?.id ? 'border-iolite/60' : ''"
        @click="open(run.id)"
      >
        <div class="flex-1 min-w-0 flex flex-col gap-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-mono text-xs text-iolite">{{ run.id }}</span>
            <span class="chip-warm">{{ areaName(run) }} L{{ run.scenario.basement.level }}</span>
            <span class="chip-warm">{{ t(`entry.mode.${run.scenario.mode}`) }}</span>
            <span class="text-[10px] text-warm-400">{{ when(run.created) }}</span>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <span
              v-for="(spec, item) in run.scenario.targets"
              :key="item"
              class="flex items-center gap-1 text-xs"
            >
              <EntityIcon :id="item" kind="items" :size="22" show-name />
              <span class="text-warm-400 font-mono text-[10px]">
                {{ spec === "min" || spec === "max" ? t(`entry.intent.${spec}`) : `${spec}/min` }}
              </span>
            </span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span
            v-for="stage in STAGES"
            :key="stage"
            class="flex items-center gap-1 text-[10px] text-warm-500"
            :title="t(`stage.${stage}`)"
          >
            <StatusDot :status="run.stages[stage].status" />
          </span>
          <button class="btn-icon text-coral" :title="t('runs.delete')" @click.stop="remove(run)">
            <span class="i-carbon-trash-can text-[12px]" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
