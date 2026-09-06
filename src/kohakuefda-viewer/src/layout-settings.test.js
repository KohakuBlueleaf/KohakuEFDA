import { createPinia, setActivePinia } from "pinia"
import { createSSRApp } from "vue"
import { renderToString } from "vue/server-renderer"
import { beforeEach, describe, expect, it } from "vitest"
import LayoutSettings from "./components/flow/LayoutSettings.vue"
import {
  PRIMARY,
  collectLayout,
  effectiveLimits,
  fieldGroups,
  layoutFields,
  layoutOutcome,
  layoutStatus,
} from "./layout-settings"
import { useAppStore } from "./stores/app"

const SHARED = {
  solver: "baseline",
  solver_options: "{}",
  seconds: 0,
  max_actions: 0,
  seed: 0,
  workers: 1,
  backend: "auto",
  frame_every: 20,
  pylon: "power_diffuser_1",
  turn_cost: 0.5,
  spread_attempts: 32000,
  spread_gap: 0,
  shrink_rounds: 200,
}
const LOCAL = {
  construction_steps: 128,
  improvement_steps: 2000,
  until_budget: true,
  candidates: 150,
  repair_actions: 12000,
  repair_route_calls: 24000,
  repack_every: 16,
  repack_gap: 1,
  layout_temperature: 0.02,
  construction_temperature: 2,
  layout_final_temperature: 1e-7,
  wire_tiebreak: 0.5,
  compaction_moves: true,
}
const CATALOG = [
  {
    name: "baseline",
    parallel: true,
    defaults: { spread_attempts: 32000, spread_gap: 0, shrink_rounds: 200 },
  },
  { name: "regional", parallel: false, defaults: { attempts: 128, shrink_rounds: 200 } },
  ...["hc", "sa"].map((name) => ({
    name,
    parallel: false,
    defaults: { ...LOCAL },
    parameter_types: { construction_temperature: "float", until_budget: "bool" },
  })),
]

function storeFor(name = "hc", last = {}) {
  const store = useAppStore()
  store.params = { layout: SHARED }
  store.solvers = CATALOG
  store.run = {
    id: "r",
    busy: false,
    stages: { layout: { status: "done", params: { solver: name, ...last } } },
  }
  return store
}

beforeEach(() => setActivePinia(createPinia()))

describe("catalog-driven layout controls", () => {
  it("promotes real budgets, retains every solver knob, and hides irrelevant controls", () => {
    const fields = layoutFields(SHARED, CATALOG, "hc")
    const keys = fields.map((f) => f.key)
    for (const key of Object.keys(LOCAL)) expect(keys).toContain(key)
    for (const key of [
      "seconds",
      "max_actions",
      "backend",
      "seed",
      "until_budget",
      "construction_steps",
      "improvement_steps",
    ]) {
      expect(keys).toContain(key)
      expect(PRIMARY).toContain(key)
    }
    expect(keys).not.toContain("spread_attempts")
    expect(keys).not.toContain("shrink_rounds")
    expect(keys).not.toContain("workers")
    expect(layoutFields(SHARED, CATALOG, "baseline").map((f) => f.key)).toContain("workers")
    expect(fields.find((f) => f.key === "construction_temperature").type).toBe("float")
    expect(
      fieldGroups(fields).flatMap((g) => g.fields).length +
        keys.filter((key) => PRIMARY.includes(key)).length,
    ).toBe(keys.length)
  })

  it("serializes typed settings with solver options winning over legacy flat values", () => {
    const draft = {
      ...SHARED,
      solver: "hc",
      workers: 4,
      spread_attempts: 65536,
      seconds: "300",
      solver_options: JSON.stringify({
        until_budget: false,
        construction_temperature: "2.5",
        repack_gap: "2",
      }),
    }
    const payload = collectLayout(SHARED, CATALOG, draft)
    expect(payload.seconds).toBe(300)
    expect(payload.workers).toBe(1)
    expect(payload).not.toHaveProperty("spread_attempts")
    expect(payload).not.toHaveProperty("construction_steps")
    expect(JSON.parse(payload.solver_options)).toMatchObject({
      until_budget: false,
      construction_temperature: 2.5,
      repack_gap: 2,
    })
    const baseline = collectLayout(SHARED, CATALOG, {
      ...SHARED,
      solver_options: '{"spread_attempts":17}',
    })
    expect(JSON.parse(baseline.solver_options).spread_attempts).toBe(17)
    expect(baseline).not.toHaveProperty("spread_attempts")
  })

  it("warns that zero global budgets still leave finite step caps", () => {
    const draft = { ...SHARED, solver: "hc" }
    expect(effectiveLimits(collectLayout(SHARED, CATALOG, draft)).untilBudget).toBe(false)
    expect(
      effectiveLimits(collectLayout(SHARED, CATALOG, { ...draft, seconds: 300 })).untilBudget,
    ).toBe(true)
    expect(
      effectiveLimits(collectLayout(SHARED, CATALOG, { ...draft, max_actions: 100 })).untilBudget,
    ).toBe(true)
  })

  it.each(["[]", "null", "{", '{"unknown":1}', '{"until_budget":"false"}', '{"repack_every":1.5}'])(
    "rejects invalid solver JSON/values %s",
    (solver_options) => {
      expect(() =>
        collectLayout(SHARED, CATALOG, { ...SHARED, solver: "hc", solver_options }),
      ).toThrow()
    },
  )

  it.each(["", -1, Infinity, "NaN"])("rejects invalid global budget %s", (seconds) => {
    expect(() => collectLayout(SHARED, CATALOG, { ...SHARED, solver: "hc", seconds })).toThrow()
  })

  it("preserves per-solver drafts when switching without carrying wrong options", () => {
    const store = storeFor("baseline", { spread_attempts: 99 })
    const draft = store.draftParams("layout")
    draft.seconds = 300
    store.switchDraftSolver("sa")
    expect(JSON.parse(draft.solver_options)).not.toHaveProperty("spread_attempts")
    draft.solver_options = '{"layout_temperature":0.1,"until_budget":false}'
    store.switchDraftSolver("baseline")
    expect(JSON.parse(draft.solver_options).spread_attempts).toBe(99)
    expect(draft.seconds).toBe(300)
    store.switchDraftSolver("sa")
    expect(JSON.parse(draft.solver_options).until_budget).toBe(false)
    expect(JSON.parse(draft.solver_options).layout_temperature).toBe(0.1)
  })

  it("renders boolean fields as checkboxes and the budget warning above advanced groups", async () => {
    storeFor()
    const app = createSSRApp(LayoutSettings)
    app.use(createPinia())
    const store = useAppStore(app.config.globalProperties.$pinia)
    store.params = { layout: SHARED }
    store.solvers = CATALOG
    store.drafts.layout = { ...SHARED, solver: "hc" }
    const html = await renderToString(app)
    expect(html).toContain('data-setting="seconds"')
    expect(html).toContain('data-setting="max_actions"')
    expect(html).toContain('type="checkbox"')
    expect(html).toContain("No global budget")
    expect(html).not.toContain('data-setting="spread_attempts"')
    expect(html.indexOf('data-setting="seconds"')).toBeLessThan(html.indexOf("<details"))
  })
})

describe("layout outcomes", () => {
  it("does not call budget exhaustion a failure when a routed result survives", () => {
    const state = {
      status: "done",
      outcome: { status: "budget_exhausted", routed: true, placed: 123, total: 123 },
    }
    expect(layoutStatus(state)).toBe("done")
    expect(layoutOutcome(state).status).toBe("budget_exhausted")
  })

  it("classifies legacy partial final frames as incomplete, without claiming too large", () => {
    const state = { status: "done", params: { seconds: 0 }, started: 1, finished: 5 }
    const frames = [
      {
        kind: "final",
        status: "no_solution_found",
        evidence: { routed: false },
        placed: 121,
        total: 123,
        fits: false,
      },
    ]
    expect(layoutStatus(state, frames)).toBe("incomplete")
    expect(layoutOutcome(state, frames)).toMatchObject({
      status: "no_solution_found",
      placed: 121,
      total: 123,
    })
    expect(layoutStatus({ status: "failed" }, frames)).toBe("failed")
    expect(layoutStatus({ status: "running" }, frames)).toBe("running")
  })
})
