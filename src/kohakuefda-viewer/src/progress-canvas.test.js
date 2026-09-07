import { expect, it } from "vitest"
import { flowDimensions, palette } from "./draw"
import { drawProgressLayout } from "./progress-draw"

it("draws historical machine positions and both boundaries across workspace expansion", () => {
  const calls = []
  const context = new Proxy(
    {},
    {
      get(target, key) {
        if (key in target) return target[key]
        return (...args) => calls.push({ op: key, args, colour: target.strokeStyle })
      },
      set(target, key, value) {
        target[key] = value
        return true
      },
    },
  )
  const first = {
    kind: "build",
    grid: [90, 90],
    area: [10, 10, 80, 80],
    target_area: [10, 10, 60, 60],
    layout: {
      width: 90,
      height: 90,
      area: [10, 10, 80, 80],
      machines: [{ id: "a", machine_id: "block", x: 65, y: 20, rotation: 0 }],
      units: [],
      segments: [],
      entries: [],
      modules: [],
    },
  }
  const dataset = { machines: { block: { width: 2, depth: 3, ports: [], modes: [] } } }
  const p = palette(false)
  const options = { showLabels: false, showItems: false }
  drawProgressLayout(context, first, dataset, 4, p, options)
  expect(flowDimensions(first, null, [50, 50])).toEqual([90, 90])
  expect(calls.some((c) => c.op === "fillRect" && c.args[0] === 261 && c.args[1] === 81)).toBe(true)
  expect(
    calls.some((c) => c.op === "strokeRect" && c.colour === p.selection && c.args[2] === 279),
  ).toBe(true)
  expect(
    calls.some((c) => c.op === "strokeRect" && c.colour === p.areaEdge && c.args[2] === 199),
  ).toBe(true)
  const expanded = {
    ...first,
    grid: [110, 110],
    area: [10, 10, 100, 100],
    layout: {
      ...first.layout,
      width: 110,
      height: 110,
      area: [10, 10, 100, 100],
      machines: [{ ...first.layout.machines[0], x: 80 }],
    },
  }
  calls.length = 0
  drawProgressLayout(context, expanded, dataset, 4, p, options)
  expect(flowDimensions(expanded, null, [50, 50])).toEqual([110, 110])
  expect(calls.some((c) => c.op === "fillRect" && c.args[0] === 321)).toBe(true)
  expect(calls.filter((c) => c.op === "strokeRect" && c.colour === p.selection)).toHaveLength(1)
  calls.length = 0
  drawProgressLayout(context, first, dataset, 4, p, options)
  expect(calls.some((c) => c.op === "fillRect" && c.args[0] === 261)).toBe(true)
})
