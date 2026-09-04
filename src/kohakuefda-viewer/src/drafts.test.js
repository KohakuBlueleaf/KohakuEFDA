import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"
import { useAppStore } from "./stores/app"

const DEFAULTS = { layout: { iterations: 4000, w_wire: 1, pylon: "power_diffuser_1" } }

function runWith(params) {
  return {
    id: "r1",
    busy: false,
    stages: { plan: { status: "done", params: {} }, layout: { status: "done", params } },
  }
}

describe("stage settings drafts", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("seeds a draft from the run's last parameters, else the defaults", () => {
    const store = useAppStore()
    store.params = DEFAULTS
    store.run = runWith({ iterations: 200, w_wire: 0 })
    expect(store.draftParams("layout")).toEqual({
      iterations: 200,
      w_wire: 0,
      pylon: "power_diffuser_1",
    })
  })

  it("keeps what was typed when stage events arrive and resets only on request", async () => {
    const store = useAppStore()
    store.params = DEFAULTS
    store.run = runWith({ iterations: 200, w_wire: 0 })
    const draft = store.draftParams("layout")
    draft.w_wire = 2.5
    await store.onEvent("r1", {
      seq: 5,
      time: 1,
      kind: "stage",
      stage: "layout",
      data: { status: "done", params: { iterations: 200, w_wire: 0 }, error: "" },
    })
    expect(store.draftParams("layout").w_wire).toBe(2.5)
    expect(store.resetDraft("layout")).toEqual(DEFAULTS.layout)
    expect(store.draftParams("layout").w_wire).toBe(1)
  })
})
