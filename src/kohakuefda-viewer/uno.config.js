import { defineConfig, presetAttributify, presetIcons, presetWind3 } from "unocss"

export default defineConfig({
  presets: [
    presetWind3(),
    presetAttributify(),
    presetIcons({
      scale: 1.2,
      extraProperties: { display: "inline-block", "vertical-align": "middle" },
    }),
  ],
  safelist: [
    "i-carbon-cube",
    "i-carbon-rain-drop",
    "i-carbon-cloud",
    "i-carbon-industry",
    "i-carbon-flow",
    "i-carbon-chart-relationship",
    "i-carbon-assembly-cluster",
    "i-carbon-apps",
    "i-carbon-connect",
    "i-carbon-checkmark-outline",
    "bg-aquamarine",
    "bg-amber",
    "bg-coral",
    "bg-warm-400",
    "bg-iolite",
    "text-aquamarine",
    "text-amber",
    "text-coral",
    "text-iolite",
    "text-sage",
    "text-sapphire",
    "text-taaffeite",
    "border-aquamarine/40",
    "border-amber/40",
    "border-coral/40",
    "border-iolite/40",
  ],
  theme: {
    colors: {
      sapphire: { light: "#D6E3F8", DEFAULT: "#0F52BA", shadow: "#082567" },
      aquamarine: { light: "#D4EDE8", DEFAULT: "#4C9989", shadow: "#1B6B5A" },
      taaffeite: { light: "#E8D5ED", DEFAULT: "#A57EAE", shadow: "#6B4670" },
      iolite: { light: "#DDD0F0", DEFAULT: "#5A4FCF", shadow: "#312A7A" },
      amber: { light: "#F5E6C8", DEFAULT: "#D4920A", shadow: "#8B5E00" },
      coral: { light: "#F5D5D5", DEFAULT: "#D46B6B", shadow: "#8B3A3A" },
      sage: { light: "#D5E8DA", DEFAULT: "#5A9E6F", shadow: "#3A6B48" },
      warm: {
        50: "#F7F5F2",
        100: "#EFECE7",
        200: "#E0DBD4",
        300: "#C5BFB7",
        400: "#A09A92",
        500: "#8A8480",
        600: "#6A645F",
        700: "#4A4540",
        800: "#3A3632",
        900: "#2A2724",
        950: "#1A1816",
      },
    },
  },
  shortcuts: {
    card: "bg-white dark:bg-warm-900 rounded-xl border border-warm-200/60 dark:border-warm-700/60",
    "card-hover":
      "card hover:border-warm-300/80 dark:hover:border-warm-600/60 hover:shadow-sm transition-all cursor-pointer",
    "btn-primary":
      "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-iolite text-white hover:bg-iolite-shadow transition-colors font-medium text-sm border-none disabled:opacity-50 disabled:cursor-not-allowed",
    "btn-secondary":
      "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-warm-100 dark:bg-warm-800 text-warm-700 dark:text-warm-300 hover:bg-warm-200 dark:hover:bg-warm-700 transition-colors font-medium text-sm border border-warm-200/50 dark:border-warm-700/50 disabled:opacity-50 disabled:cursor-not-allowed",
    "btn-ghost":
      "inline-flex items-center gap-1 px-2 py-1 rounded-md text-warm-600 dark:text-warm-300 hover:bg-warm-200/60 dark:hover:bg-warm-800/60 transition-colors text-xs disabled:opacity-50 disabled:cursor-not-allowed",
    "btn-icon":
      "w-7 h-7 inline-flex items-center justify-center rounded-md text-warm-500 hover:text-warm-800 dark:hover:text-warm-200 hover:bg-warm-200/60 dark:hover:bg-warm-800/60 transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
    chip: "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium leading-4",
    "chip-iolite": "chip bg-iolite/10 text-iolite-shadow dark:text-iolite-light",
    "chip-aqua": "chip bg-aquamarine/10 text-aquamarine-shadow dark:text-aquamarine-light",
    "chip-amber": "chip bg-amber/10 text-amber-shadow dark:text-amber-light",
    "chip-coral": "chip bg-coral/10 text-coral-shadow dark:text-coral-light",
    "chip-sage": "chip bg-sage/10 text-sage-shadow dark:text-sage-light",
    "chip-sapphire": "chip bg-sapphire/10 text-sapphire-shadow dark:text-sapphire-light",
    "chip-taaffeite": "chip bg-taaffeite/10 text-taaffeite-shadow dark:text-taaffeite-light",
    "chip-warm": "chip bg-warm-100 dark:bg-warm-800 text-warm-600 dark:text-warm-300",
    "input-field":
      "px-2.5 py-1.5 rounded-lg bg-warm-50 dark:bg-warm-900 border border-warm-200 dark:border-warm-700 text-warm-800 dark:text-warm-200 placeholder-warm-400 dark:placeholder-warm-600 focus:outline-none focus:border-iolite dark:focus:border-iolite-light transition-colors text-sm",
    "input-number":
      "input-field w-24 text-right font-mono tabular-nums px-2 py-1 text-xs",
    "select-field":
      "input-field appearance-none pr-6 cursor-pointer",
    "section-title":
      "text-[10px] uppercase tracking-wider text-warm-500 dark:text-warm-400 font-medium",
    "text-secondary": "text-xs text-warm-500 dark:text-warm-400",
    "text-body": "text-sm text-warm-800 dark:text-warm-200",
    "panel-header":
      "flex items-center gap-1.5 px-3 h-8 border-b border-warm-200/70 dark:border-warm-700/70 bg-warm-100/60 dark:bg-warm-900/60 text-[11px] text-warm-500 dark:text-warm-400 shrink-0",
    "seg-group":
      "inline-flex rounded-lg border border-warm-200 dark:border-warm-700 overflow-hidden text-xs",
    "seg-item":
      "px-2.5 py-1 text-warm-600 dark:text-warm-300 hover:bg-warm-100 dark:hover:bg-warm-800 transition-colors cursor-pointer",
    "seg-item-active": "seg-item !bg-iolite !text-white",
    "table-base": "w-full text-xs border-collapse",
    "table-th":
      "text-left font-medium text-[10px] uppercase tracking-wider text-warm-500 dark:text-warm-400 px-2 py-1.5 border-b border-warm-200 dark:border-warm-700 whitespace-nowrap",
    "table-td":
      "px-2 py-1.5 border-b border-warm-200/60 dark:border-warm-700/60 text-warm-700 dark:text-warm-300 whitespace-nowrap align-top",
  },
})
