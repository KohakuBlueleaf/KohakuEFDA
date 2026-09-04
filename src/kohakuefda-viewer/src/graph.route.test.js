import { describe, expect, it } from "vitest"
import {
  findCrossings,
  labelAnchor,
  layerGraph,
  pathWithJumps,
  routeEdges,
  segmentsOf,
} from "./graph"

const METRICS = { nodeW: 100, nodeH: 40, rowH: 60, gapMin: 80, track: 10, stub: 10, margin: 20 }

function orthogonal(points) {
  for (let n = 0; n + 1 < points.length; n += 1) {
    const a = points[n]
    const b = points[n + 1]
    expect(a.x === b.x || a.y === b.y).toBe(true)
  }
}

describe("routeEdges", () => {
  it("draws an unavoidable crossing once and marks it with a hop", () => {
    const edges = [
      { source: "a", target: "c" },
      { source: "a", target: "d" },
      { source: "b", target: "c" },
      { source: "b", target: "d" },
    ]
    const layout = layerGraph(["a", "b", "c", "d"], edges)
    const routed = routeEdges(layout, edges, METRICS)
    expect(routed.crossings).toHaveLength(1)
    const hopped = pathWithJumps(routed.routes.get(routed.crossings[0].edge), routed.crossings, 4)
    expect(hopped).toContain(" A 4 4 0 0 ")
    for (const points of routed.routes.values()) {
      orthogonal(points)
    }
  })

  it("gives parallel edges separate tracks without crossings", () => {
    const edges = [
      { source: "a", target: "c" },
      { source: "b", target: "d" },
      { source: "a", target: "d" },
    ]
    const layout = layerGraph(["a", "b", "c", "d"], edges)
    const routed = routeEdges(layout, edges, METRICS)
    expect(routed.crossings).toEqual([])
    const tracks = new Set(
      [...routed.routes.values()].map(
        (points) => segmentsOf(points).find((s) => s.kind === "v")?.x,
      ),
    )
    expect(tracks.size).toBeGreaterThanOrEqual(2)
  })

  it("puts a dummy in the middle column of a long edge and routes around nodes", () => {
    const edges = [
      { source: "a", target: "b" },
      { source: "b", target: "c" },
      { source: "a", target: "c" },
    ]
    const layout = layerGraph(["a", "b", "c"], edges)
    expect(layout.dummies.size).toBe(1)
    const [dummy] = layout.dummies.values()
    expect(dummy.column).toBe(1)
    expect(dummy.row).not.toBe(layout.position.get("b").row)
    const routed = routeEdges(layout, edges, METRICS)
    const long = routed.routes.get(2)
    const b = routed.nodeAt.get("b")
    for (const s of segmentsOf(long)) {
      if (s.kind === "h") {
        expect(
          s.y <= b.y || s.y >= b.y + METRICS.nodeH || s.x1 <= b.x || s.x0 >= b.x + METRICS.nodeW,
        ).toBe(true)
      }
    }
  })

  it("returns back edges under the graph", () => {
    const edges = [
      { source: "a", target: "b" },
      { source: "b", target: "a" },
    ]
    const layout = layerGraph(["a", "b"], edges)
    expect(layout.back.size).toBe(1)
    const routed = routeEdges(layout, edges, METRICS)
    const [back] = layout.back
    const points = routed.routes.get(back)
    const lowest = Math.max(...points.map((p) => p.y))
    expect(lowest).toBeGreaterThan(METRICS.margin + layout.rows * METRICS.rowH - METRICS.rowH / 2)
    expect(routed.height).toBeGreaterThan(lowest)
  })

  it("labels the longest horizontal run or the vertical when runs are short", () => {
    const flat = [
      { x: 0, y: 10 },
      { x: 200, y: 10 },
    ]
    expect(labelAnchor(flat, 50)).toEqual({ x: 100, y: 10, along: "h" })
    const tall = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 100 },
      { x: 20, y: 100 },
    ]
    expect(labelAnchor(tall, 50)).toEqual({ x: 10, y: 50, along: "v" })
    expect(findCrossings(new Map([[0, flat]]))).toEqual([])
  })
})
