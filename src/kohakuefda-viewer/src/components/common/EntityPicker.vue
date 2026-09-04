<script setup>
import { useI18n } from "@/i18n"
import { pickName } from "@/i18n/names"
import { useAppStore } from "@/stores/app"

const props = defineProps({
  open: { type: Boolean, default: false },
  kind: { type: String, default: "items" },
  candidates: { type: Array, default: null },
  title: { type: String, default: "" },
  exclude: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:open", "select"])
const { t } = useI18n()
const store = useAppStore()

const query = ref("")
const phase = ref("all")
const input = ref(null)
const PHASES = [
  { key: "all", value: null },
  { key: "solid", value: 1 },
  { key: "liquid", value: 2 },
  { key: "gas", value: 4 },
]

const entries = computed(() => {
  const table = store.dataset?.[props.kind] ?? {}
  const ids = props.candidates ?? Object.keys(table)
  const excluded = new Set(props.exclude)
  const wanted = PHASES.find((p) => p.key === phase.value)?.value ?? null
  const needle = query.value.trim().toLowerCase()
  return ids
    .filter((id) => table[id] && !excluded.has(id))
    .map((id) => ({
      id,
      name: pickName(table[id].names, store.lang) || id,
      en: table[id].names?.en ?? "",
      phase: table[id].phase,
    }))
    .filter((e) => wanted === null || props.kind !== "items" || e.phase === wanted)
    .filter(
      (e) =>
        !needle ||
        e.name.toLowerCase().includes(needle) ||
        e.en.toLowerCase().includes(needle) ||
        e.id.includes(needle),
    )
    .sort((a, b) => a.name.localeCompare(b.name))
})

function close() {
  emit("update:open", false)
}

function choose(id) {
  emit("select", id)
  close()
}

function onKey(event) {
  if (event.key === "Escape") {
    close()
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      query.value = ""
      phase.value = "all"
      nextTick(() => input.value?.focus())
      document.addEventListener("keydown", onKey)
    } else {
      document.removeEventListener("keydown", onKey)
    }
  },
)
onUnmounted(() => document.removeEventListener("keydown", onKey))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      @click.self="close"
    >
      <div
        class="bg-warm-50 dark:bg-warm-950 rounded-xl shadow-xl border border-warm-200 dark:border-warm-700 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden"
      >
        <header
          class="flex items-center gap-3 px-4 py-3 border-b border-warm-200 dark:border-warm-700"
        >
          <h3 class="text-sm font-medium text-warm-800 dark:text-warm-200">{{ title }}</h3>
          <input
            ref="input"
            v-model="query"
            class="input-field flex-1"
            :placeholder="t('picker.search')"
          />
          <div v-if="kind === 'items'" class="seg-group">
            <button
              v-for="option in PHASES"
              :key="option.key"
              :class="phase === option.key ? 'seg-item-active' : 'seg-item'"
              @click="phase = option.key"
            >
              {{ t(`picker.${option.key}`) }}
            </button>
          </div>
          <button class="btn-icon" @click="close"><span class="i-carbon-close" /></button>
        </header>
        <div class="flex-1 overflow-y-auto p-4">
          <p v-if="!entries.length" class="text-secondary text-center py-8">
            {{ t("picker.none") }}
          </p>
          <div
            v-else
            class="grid gap-2"
            style="grid-template-columns: repeat(auto-fill, minmax(150px, 1fr))"
          >
            <button
              v-for="entry in entries"
              :key="entry.id"
              class="card-hover p-2 flex items-center gap-2 text-left"
              @click="choose(entry.id)"
            >
              <EntityIcon :id="entry.id" :kind="kind" :size="36" />
              <span class="min-w-0">
                <span class="block text-xs font-medium text-warm-800 dark:text-warm-200 truncate">
                  {{ entry.name }}
                </span>
                <span class="block text-[10px] text-warm-400 font-mono truncate">{{
                  entry.id
                }}</span>
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
