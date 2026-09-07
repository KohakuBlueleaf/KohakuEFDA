import { createPinia, setActivePinia } from "pinia"
import { createSSRApp, createRenderer, h, nextTick, ref } from "vue"
import { renderToString } from "vue/server-renderer"
import { beforeEach, describe, expect, it, vi } from "vitest"
import LayoutProgress from "./components/flow/LayoutProgress.vue"
import CostChart from "./components/canvas/CostChart.vue"
import { useTimeline } from "./composables/timeline"
import { useAppStore } from "./stores/app"
import { flowDimensions } from "./draw"
import {
  chartGeometry,
  frameSpace,
  progressFrames,
  progressOf,
  progressSeries,
  useFinalArtifact,
} from "./progress"

const CATALOGUE = {
  kind: "catalogue",
  grid: [70, 70],
  area: [10, 10, 60, 60],
  target_area: [10, 10, 60, 60],
}
const FRAME = {
  frame_schema: 1,
  kind: "improve",
  phase: "compaction",
  domain: "workspace",
  display: "current",
  grid: [90, 90],
  area: [10, 10, 80, 80],
  target_area: [10, 10, 60, 60],
  blocks: [["a", 65, 20, 0]],
  placed: 70,
  total: 70,
  elapsed: 30,
  workspace_routed: true,
  clean: false,
  terms: { area: 3500, width: 60, height: 59, target_overflow: 400 },
  best: {
    state_id: "best",
    domain: "workspace",
    missing: 0,
    terms: { area: 3400, target_overflow: 350 },
  },
  work: { actions: 400, route_calls: 800 },
  evidence: { routed: false, rates: "not_checked" },
}

beforeEach(() => setActivePinia(createPinia()))

describe("self-contained progress and compatibility", () => {
  it("uses each expansion's geometry, not the initial catalogue or final board", () => {
    expect(flowDimensions(FRAME, CATALOGUE, [50, 50])).toEqual([90, 90])
    const enlarged = { ...FRAME, grid: [110, 110], area: [10, 10, 100, 100] }
    expect(flowDimensions(enlarged, CATALOGUE, [50, 50])).toEqual([110, 110])
    expect(frameSpace(enlarged, CATALOGUE).target).toEqual([10, 10, 60, 60])
    expect(flowDimensions({ rect: [10, 10, 90, 95] }, CATALOGUE, [50, 50])).toEqual([92, 97])
    expect(progressFrames([null, CATALOGUE, FRAME, { kind: "worker" }])).toEqual([FRAME])
  })

  it("never promotes a workspace or unchecked old frame to target success", () => {
    expect(progressOf({ ...FRAME, clean: true, evidence: { routed: true } }).routed).toBe(false)
    expect(progressOf(FRAME).workspaceRouted).toBe(true)
    expect(progressOf({ kind: "build", blocks: [], fits: true }).routed).toBe(false)
    expect(progressOf({ kind: "final", blocks: [], clean: true }).routed).toBe(true)
    expect(progressOf(null)).toBe(null)
  })

  it("does not let final artifacts obscure playback or a live rerun", () => {
    const state = {
      showFinal: true,
      playing: false,
      live: true,
      index: 9,
      count: 10,
      running: false,
    }
    expect(useFinalArtifact(state)).toBe(true)
    for (const change of [
      { playing: true },
      { live: false },
      { index: 2 },
      { running: true },
      { showFinal: false },
    ])
      expect(useFinalArtifact({ ...state, ...change })).toBe(false)
  })

  it("keeps current and best curves separate, with truthful gaps and elapsed spacing", () => {
    const frames = [
      FRAME,
      { ...FRAME, elapsed: 90, terms: { area: 3600, target_overflow: 450 } },
      { ...FRAME, elapsed: 100, display: "worker" },
      { ...FRAME, elapsed: 120, terms: { area: 3200, target_overflow: 100 } },
    ]
    const series = progressSeries(frames, "target_overflow")
    expect(series[0].values).toEqual([
      { x: 30, y: 400 },
      { x: 90, y: 450 },
      null,
      { x: 120, y: 100 },
    ])
    expect(series[1].values[1].y).toBe(350)
    const geometry = chartGeometry(series, 400, 100, 90)
    expect(geometry.lines[0].path.match(/M/g)).toHaveLength(2)
    expect(geometry.cursorX).toBeCloseTo(4 + (392 * 60) / 90)
    expect(geometry.lines[0].path).not.toMatch(/NaN|Infinity/)
    expect(chartGeometry([{ values: [null, NaN] }], 400, 100).lines).toEqual([])
  })

  it.each(["en", "zh-TW", "zh-CN"])(
    "renders truthful workspace and target status in %s",
    async (lang) => {
      useAppStore().lang = lang
      const app = createSSRApp(LayoutProgress, { frame: FRAME, frames: [FRAME] })
      app.component("CostChart", CostChart)
      const html = await renderToString(app)
      expect(html).toContain("70 / 70")
      expect(html).toContain("50×50")
      expect(html).toContain("70×70")
      expect(html).toContain("400")
      expect(html).toContain("350")
      expect(html).toContain("not_checked")
      expect(html).not.toContain("progress.phase")
    },
  )

  it("receives indexed SSE frames idempotently and ignores old runs", async () => {
    const store = useAppStore()
    store.run = { id: "new", stages: { layout: { status: "running" } }, busy: true }
    const event = { kind: "frame", stage: "layout", index: 0, data: FRAME }
    await store.onEvent("new", event)
    await store.onEvent("new", event)
    await store.onEvent("old", { ...event, index: 1 })
    expect(store.frames.layout).toEqual([FRAME])
    const saved = JSON.parse(JSON.stringify(store.frames.layout))
    expect(progressOf(saved[0])).toEqual(progressOf(FRAME))
  })
})

it("timeline resumes live immediately and resets on a same-length run switch", async () => {
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn(() => 1),
  )
  vi.stubGlobal("cancelAnimationFrame", vi.fn())
  const renderer = createRenderer({
    createElement: () => ({}),
    createText: () => ({}),
    createComment: () => ({}),
    insert: () => {},
    remove: () => {},
    setText: () => {},
    setElementText: () => {},
    parentNode: () => null,
    nextSibling: () => null,
    patchProp: () => {},
  })
  const frames = ref([{}, {}, {}])
  let timeline
  const app = renderer.createApp({
    setup() {
      timeline = useTimeline(frames)
      return () => h("div")
    },
  })
  app.mount({})
  expect(timeline.index.value).toBe(2)
  timeline.live.value = false
  timeline.index.value = 0
  frames.value.push({})
  await nextTick()
  expect(timeline.index.value).toBe(0)
  timeline.live.value = true
  await nextTick()
  expect(timeline.index.value).toBe(3)
  timeline.playing.value = true
  await nextTick()
  expect(timeline.index.value).toBe(0)
  expect(timeline.live.value).toBe(false)
  timeline.index.value = 2
  frames.value = [{}, {}, {}, {}]
  await nextTick()
  expect(timeline.index.value).toBe(0)
  expect(timeline.playing.value).toBe(false)
  app.unmount()
  vi.unstubAllGlobals()
})
