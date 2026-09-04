<script setup>
const props = defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, required: true },
  filter: { type: String, default: "" },
})

const visible = computed(() => {
  const needle = props.filter.trim().toLowerCase()
  if (!needle) {
    return props.rows
  }
  return props.rows.filter((row) =>
    props.columns.some((column) =>
      String(row[column.key] ?? "")
        .toLowerCase()
        .includes(needle),
    ),
  )
})
const TONE = {
  error: "text-coral",
  warning: "text-amber-shadow dark:text-amber",
  info: "text-sapphire dark:text-sapphire-light",
}

defineExpose({ visible })
</script>

<template>
  <div class="overflow-x-auto card">
    <table class="table-base">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key" class="table-th">{{ column.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in visible"
          :key="row.id ?? index"
          class="hover:bg-warm-50 dark:hover:bg-warm-800/40"
        >
          <td
            v-for="column in columns"
            :key="column.key"
            class="table-td"
            :class="TONE[row.tone] ?? ''"
          >
            <slot :name="`cell-${column.key}`" :row="row">{{ row[column.key] }}</slot>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
