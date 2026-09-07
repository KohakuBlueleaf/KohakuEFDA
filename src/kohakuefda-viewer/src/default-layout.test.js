import { createPinia, setActivePinia } from "pinia"
import { expect, it } from "vitest"
import { collectLayout, effectiveLimits } from "./layout-settings"
import { useAppStore } from "./stores/app"

it("new drafts and reset use time-budgeted HC while saved settings remain intact", () => {
  setActivePinia(createPinia())
  const store = useAppStore()
  store.params = {
    layout: {
      solver: "hc",
      seconds: 600,
      max_actions: 0,
      backend: "native",
      seed: 0,
      workers: 1,
      construction_steps: 1000000,
      improvement_steps: 1000000,
      solver_options: "{}",
    },
  }
  store.solvers = [
    {
      name: "hc",
      defaults: {
        construction_steps: 128,
        improvement_steps: 2000,
        until_budget: true,
      },
    },
  ]
  const draft = store.draftParams("layout")
  const payload = collectLayout(store.params.layout, store.solvers, draft)
  expect(payload.solver).toBe("hc")
  expect(payload.seconds).toBe(600)
  expect(payload.max_actions).toBe(0)
  expect(payload.backend).toBe("native")
  expect(effectiveLimits(payload).untilBudget).toBe(true)
  expect(JSON.parse(payload.solver_options)).toEqual({
    construction_steps: 1000000,
    improvement_steps: 1000000,
    until_budget: true,
  })
  store.drafts = {}
  const last = {
    solver: "hc-tree",
    seconds: 30,
    backend: "python",
    solver_options: '{"construction_steps":17}',
  }
  store.run = { stages: { layout: { params: last } } }
  expect(store.draftParams("layout")).toMatchObject(last)
  expect(store.resetDraft("layout")).toEqual(store.params.layout)
  expect(store.run.stages.layout.params).toEqual(last)
})
