<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const router = useRouter()
const exampleName = ref("")
const fileInput = ref(null)
const steps = ["where", "what", "have", "build"]

const canBuild = computed(
  () => store.apiAvailable && Object.keys(store.scenario.targets).length > 0 && !store.runBusy,
)

async function build(through) {
  await store.newRun(through)
  router.push("/")
}

function loadExample() {
  if (exampleName.value) {
    store.applyExample(exampleName.value)
    exampleName.value = ""
  }
}

async function exportToml() {
  const text = await store.exportToml()
  const blob = new Blob([text], { type: "application/toml" })
  const link = document.createElement("a")
  link.href = URL.createObjectURL(blob)
  link.download = "scenario.toml"
  link.click()
  URL.revokeObjectURL(link.href)
}

async function importToml(event) {
  const file = event.target.files?.[0]
  if (file) {
    await store.importToml(await file.text())
  }
  event.target.value = ""
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="panel-header">
      <span class="i-carbon-edit text-[12px]" />
      <span class="font-medium text-warm-700 dark:text-warm-300">{{ t("entry.title") }}</span>
      <span class="flex-1" />
      <select
        v-model="exampleName"
        class="select-field !py-0 !text-[10px] !pr-5"
        @change="loadExample"
      >
        <option value="">{{ t("entry.examples") }}</option>
        <option v-for="example in store.examples" :key="example.name" :value="example.name">
          {{ t(`examples.${example.name}`) }}
        </option>
      </select>
      <button class="btn-icon !w-6 !h-6" :title="t('entry.import')" @click="fileInput.click()">
        <span class="i-carbon-upload text-[11px]" />
      </button>
      <input ref="fileInput" type="file" accept=".toml" hidden @change="importToml" />
      <button class="btn-icon !w-6 !h-6" :title="t('entry.export')" @click="exportToml">
        <span class="i-carbon-download text-[11px]" />
      </button>
      <button class="btn-icon !w-6 !h-6" :title="t('entry.reset')" @click="store.resetScenario()">
        <span class="i-carbon-reset text-[11px]" />
      </button>
    </div>
    <div class="flex-1 overflow-y-auto p-3 flex flex-col gap-4">
      <section v-for="(step, position) in steps" :key="step" class="flex flex-col gap-2">
        <h3 class="flex items-center gap-2 text-xs font-semibold text-warm-800 dark:text-warm-200">
          <span
            class="w-5 h-5 rounded-full bg-iolite/10 text-iolite text-[10px] flex items-center justify-center font-mono"
          >
            {{ position + 1 }}
          </span>
          {{ t(`entry.${step}`) }}
        </h3>
        <p class="text-secondary -mt-1">{{ t(`entry.${step}Hint`) }}</p>
        <WhereStep v-if="step === 'where'" />
        <WantStep v-else-if="step === 'what'" />
        <HaveStep v-else-if="step === 'have'" />
        <BuildStep v-else />
      </section>
    </div>
    <div
      class="p-3 border-t border-warm-200 dark:border-warm-700 flex flex-col gap-1.5 bg-white/60 dark:bg-warm-900/60"
    >
      <div class="flex gap-1.5">
        <button
          class="btn-primary flex-1 justify-center"
          :disabled="!canBuild"
          @click="build('netlist')"
        >
          <span class="i-carbon-flash" /> {{ t("entry.buildButton") }}
        </button>
        <button
          class="btn-secondary"
          :disabled="!canBuild"
          :title="t('entry.buildAllHint')"
          @click="build('verify')"
        >
          <span class="i-carbon-skip-forward-filled" /> {{ t("entry.buildAll") }}
        </button>
      </div>
      <p class="text-[10px] text-warm-500">{{ t("entry.buildFooter") }}</p>
      <p v-if="!store.apiAvailable" class="text-[10px] text-coral">{{ t("flow.noApi") }}</p>
    </div>
  </div>
</template>
