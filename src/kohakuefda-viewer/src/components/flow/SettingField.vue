<script setup>
import { useI18n } from "@/i18n"

const props = defineProps({
  field: { type: Object, required: true },
  value: { type: [String, Number, Boolean], default: "" },
  choices: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["change"])
const { t } = useI18n()
const label = computed(() => {
  const key = `params.${props.field.key}`
  const text = t(key)
  return text === key ? props.field.key.replaceAll("_", " ") : text
})
const help = computed(() => {
  const key = `paramHelp.${props.field.key}`
  const text = t(key)
  return text === key ? label.value : text
})
function choiceLabel(choice) {
  const key = `choices.${props.field.key}.${choice}`
  const text = t(key)
  return text === key ? choice : text
}
</script>

<template>
  <label class="flex items-center justify-between gap-2" :data-setting="field.key">
    <span class="text-warm-700 dark:text-warm-200" :title="help">{{ label }}</span>
    <select
      v-if="choices.length"
      :value="value"
      :disabled="disabled"
      class="input-number !w-36"
      @change="emit('change', $event.target.value)"
    >
      <option v-for="choice in choices" :key="choice" :value="choice">
        {{ choiceLabel(choice) }}
      </option>
    </select>
    <input
      v-else-if="field.type === 'bool'"
      type="checkbox"
      :checked="value === true"
      :disabled="disabled"
      class="accent-iolite"
      @change="emit('change', $event.target.checked)"
    />
    <input
      v-else
      :value="value"
      :type="field.type === 'str' ? 'text' : 'number'"
      :disabled="disabled"
      :min="field.key === 'seed' ? undefined : 0"
      :step="field.type === 'int' ? 1 : 'any'"
      class="input-number !w-36"
      @input="emit('change', $event.target.value)"
    />
  </label>
</template>
