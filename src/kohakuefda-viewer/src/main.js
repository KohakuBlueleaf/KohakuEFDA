import { createApp } from "vue"
import { createPinia } from "pinia"
import { createRouter, createWebHashHistory } from "vue-router"
import { routes } from "vue-router/auto-routes"
import App from "./App.vue"

import "uno.css"
import "./style.css"

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount("#app")
