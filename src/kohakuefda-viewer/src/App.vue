<script setup>
import { useAppStore } from "@/stores/app"
import { useThemeStore } from "@/stores/theme"

const store = useAppStore()
const theme = useThemeStore()

theme.init()
onMounted(() => {
  store.load()
})
</script>

<template>
  <div class="h-full flex flex-col bg-warm-50 dark:bg-warm-950 text-warm-800 dark:text-warm-200">
    <AppHeader />
    <main class="flex-1 min-h-0 overflow-hidden">
      <RouterView />
    </main>
    <StatusBar />
    <ToastCenter />
  </div>
</template>
