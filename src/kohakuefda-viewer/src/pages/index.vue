<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const entryOpen = ref(false)
const inspectorOpen = ref(false)

const view = computed(() => store.selectedStage)
</script>

<template>
  <div class="h-full flex overflow-hidden">
    <aside
      class="w-80 shrink-0 border-r border-warm-200 dark:border-warm-700 bg-white dark:bg-warm-900 flex-col h-full hidden lg:flex"
    >
      <DesignEntry />
    </aside>
    <div v-if="entryOpen" class="fixed inset-0 z-30 flex lg:hidden" @click.self="entryOpen = false">
      <aside
        class="w-80 max-w-[90vw] h-full bg-white dark:bg-warm-900 border-r border-warm-200 dark:border-warm-700 shadow-xl"
      >
        <DesignEntry />
      </aside>
      <div class="flex-1 bg-black/40" />
    </div>

    <section class="flex-1 min-w-0 flex flex-col h-full">
      <div
        class="px-3 pt-2 pb-1 flex items-center gap-2 border-b border-warm-200 dark:border-warm-700"
      >
        <button class="btn-secondary !py-1 !text-xs lg:hidden" @click="entryOpen = true">
          <span class="i-carbon-edit" /> {{ t("entry.title") }}
        </button>
        <div class="flex-1 min-w-0">
          <FlowStrip />
        </div>
        <button
          class="btn-secondary !py-1 !text-xs xl:hidden"
          @click="inspectorOpen = !inspectorOpen"
        >
          <span class="i-carbon-settings-adjust" /> {{ t("flow.inspector") }}
        </button>
      </div>
      <div class="flex-1 min-h-0 flex">
        <div class="flex-1 min-w-0 overflow-y-auto p-3">
          <p v-if="store.flowError" class="text-coral text-xs mb-2">{{ store.flowError }}</p>
          <div v-if="!store.run" class="card p-8 text-center flex flex-col items-center gap-2">
            <span class="i-carbon-industry text-3xl text-iolite" />
            <div class="text-sm font-medium">{{ t("studio.welcome") }}</div>
            <p class="text-secondary max-w-md">{{ t("studio.welcomeHint") }}</p>
          </div>
          <PlanView v-else-if="view === 'plan'" />
          <NetlistView v-else-if="view === 'netlist'" />
          <LayoutView v-else-if="view === 'layout'" />
          <VerifyView v-else />
        </div>
        <aside
          class="w-72 shrink-0 border-l border-warm-200 dark:border-warm-700 bg-white dark:bg-warm-900 h-full"
          :class="inspectorOpen ? 'flex flex-col' : 'hidden xl:flex xl:flex-col'"
        >
          <StageInspector />
        </aside>
      </div>
    </section>
  </div>
</template>
