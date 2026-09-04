<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const router = useRouter()

const columns = computed(() =>
  ["module", "origin", "size", "entities"].map((key) => ({ key, label: t(`columns.${key}`) })),
)
const rows = computed(() =>
  (store.layout?.modules ?? []).map((module) => ({
    id: module.id,
    module: module.id,
    origin: `(${module.x}, ${module.y})`,
    size: `${module.width}×${module.height}`,
    entities: module.entities.length,
  })),
)

function open(id) {
  router.push({ path: "/layout", query: { module: id } })
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-4xl mx-auto px-4 py-4 flex flex-col gap-3">
      <h1 class="text-lg font-semibold">{{ t("modules.heading") }}</h1>
      <p class="text-secondary">{{ t("modules.intro") }}</p>
      <p v-if="!store.layout" class="card p-8 text-center text-secondary">
        {{ t("status.missing") }}
      </p>
      <DataTable v-else :columns="columns" :rows="rows">
        <template #cell-module="{ row }">
          <button class="btn-ghost text-iolite" @click="open(row.id)">
            <span class="i-carbon-view" /> {{ row.id }}
          </button>
        </template>
      </DataTable>
    </div>
  </div>
</template>
