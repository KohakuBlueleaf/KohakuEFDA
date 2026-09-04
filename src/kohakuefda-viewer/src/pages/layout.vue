<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"

const { t } = useI18n()
const store = useAppStore()
const route = useRoute()
const highlight = computed(() => String(route.query.module ?? ""))
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-6xl mx-auto px-4 py-4 flex flex-col gap-3">
      <div class="flex items-center gap-3">
        <h1 class="text-lg font-semibold">{{ t("layout.heading") }}</h1>
        <span v-if="store.layout" class="text-secondary">
          {{ t("layout.square") }} {{ store.layout.width }}×{{ store.layout.height }} ·
          {{ store.layout.notes }}
        </span>
      </div>
      <VerifyView :key="highlight" :highlight="highlight" />
    </div>
  </div>
</template>
