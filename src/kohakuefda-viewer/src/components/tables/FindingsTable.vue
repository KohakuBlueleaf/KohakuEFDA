<script setup>
import { useI18n } from "@/i18n"

const props = defineProps({
  findings: { type: Array, required: true },
})
const { t } = useI18n()

const columns = computed(() =>
  ["severity", "rule", "subject", "message"].map((key) => ({
    key,
    label: t(`columns.${key}`),
  })),
)
const rows = computed(() =>
  props.findings.map((finding, index) => ({ id: index, tone: finding.severity, ...finding })),
)
const CHIP = { error: "chip-coral", warning: "chip-amber", info: "chip-sapphire" }
</script>

<template>
  <DataTable :columns="columns" :rows="rows">
    <template #cell-severity="{ row }">
      <span :class="CHIP[row.severity]">{{ t(`severity.${row.severity}`) }}</span>
    </template>
    <template #cell-message="{ row }">
      <span class="whitespace-normal">{{ row.message }}</span>
    </template>
  </DataTable>
</template>
