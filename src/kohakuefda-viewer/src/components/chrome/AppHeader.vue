<script setup>
import { useI18n } from "@/i18n"
import { useAppStore } from "@/stores/app"
import { useThemeStore } from "@/stores/theme"

const { t, lang, languages, setLang } = useI18n()
const store = useAppStore()
const theme = useThemeStore()
const primary = [
  { key: "studio", path: "/" },
  { key: "runs", path: "/runs" },
  { key: "dataset", path: "/dataset" },
]
const results = [
  { key: "plan", path: "/plan" },
  { key: "layout", path: "/layout" },
  { key: "modules", path: "/modules" },
  { key: "report", path: "/report" },
]
</script>

<template>
  <header
    class="flex items-center gap-2 px-3 h-8 border-b border-warm-200 dark:border-warm-700 bg-white dark:bg-warm-900 text-xs shrink-0"
  >
    <RouterLink
      to="/"
      class="flex items-center gap-1.5 font-semibold text-warm-800 dark:text-warm-200"
    >
      <span class="i-carbon-industry text-iolite text-[14px]" />
      {{ t("app.title") }}
    </RouterLink>
    <span v-if="store.dataset" class="chip-warm font-mono">{{ store.dataset.version.id }}</span>
    <div class="seg-sep" />
    <nav class="flex items-center gap-0.5">
      <RouterLink
        v-for="page in primary"
        :key="page.key"
        :to="page.path"
        class="px-2 py-0.5 rounded text-warm-500 hover:text-warm-800 dark:hover:text-warm-200 transition-colors"
        :active-class="page.path === '/' ? 'router-link-active' : '!text-iolite bg-iolite/10'"
        :exact-active-class="
          page.path === '/' ? '!text-iolite bg-iolite/10' : 'router-link-exact-active'
        "
      >
        {{ t(`nav.${page.key}`) }}
      </RouterLink>
    </nav>
    <div class="seg-sep" />
    <nav class="flex items-center gap-0.5">
      <RouterLink
        v-for="page in results"
        :key="page.key"
        :to="page.path"
        class="px-2 py-0.5 rounded text-warm-400 hover:text-warm-700 dark:hover:text-warm-300 transition-colors"
        active-class="!text-iolite bg-iolite/10"
      >
        {{ t(`nav.${page.key}`) }}
      </RouterLink>
    </nav>
    <div class="flex-1" />
    <RouterLink
      v-if="store.run"
      to="/"
      class="flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-mono"
      :class="
        store.runBusy
          ? 'border-aquamarine/40 text-aquamarine'
          : 'border-warm-200 dark:border-warm-700 text-warm-500'
      "
    >
      <StatusDot :status="store.runBusy ? 'running' : 'done'" />
      {{ store.run.id }}
      <span v-if="store.activeStage">· {{ t(`stage.${store.activeStage}`) }}…</span>
    </RouterLink>
    <div class="seg-sep" />
    <div class="seg-group">
      <button
        v-for="code in languages"
        :key="code"
        :class="code === lang ? 'seg-item-active' : 'seg-item'"
        @click="setLang(code)"
      >
        {{ t(`lang.${code}`) }}
      </button>
    </div>
    <button class="btn-icon" :title="t('app.theme')" @click="theme.toggle()">
      <span :class="theme.dark ? 'i-carbon-sun' : 'i-carbon-moon'" class="text-[13px]" />
    </button>
  </header>
</template>

<style scoped>
.seg-sep {
  width: 1px;
  height: 14px;
  background: currentColor;
  opacity: 0.12;
  flex-shrink: 0;
}
</style>
