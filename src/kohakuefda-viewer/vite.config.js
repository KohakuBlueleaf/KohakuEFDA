import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import VueRouter from "unplugin-vue-router/vite"
import AutoImport from "unplugin-auto-import/vite"
import Components from "unplugin-vue-components/vite"
import { VueRouterAutoImports } from "unplugin-vue-router"
import { ElementPlusResolver } from "unplugin-vue-components/resolvers"
import UnoCSS from "unocss/vite"
import { fileURLToPath, URL } from "node:url"

export default defineConfig({
  base: "./",
  plugins: [
    VueRouter({
      routesFolder: "src/pages",
    }),
    vue(),
    UnoCSS(),
    AutoImport({
      imports: ["vue", "pinia", VueRouterAutoImports],
      resolvers: [ElementPlusResolver()],
      dts: false,
    }),
    Components({
      dirs: ["src/components"],
      resolvers: [ElementPlusResolver()],
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
  build: {
    outDir: "../kohakuefda/web_dist",
    emptyOutDir: true,
  },
})
