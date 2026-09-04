import { describe, expect, it } from "vitest"
import edges from "./fixtures/plan_edges_copper_gas.json"
import { layerGraph, routeEdges, segmentsOf } from "./graph"

// A recorded player's plan (Cuprium Part with gas on and no water offered): a supply node sits
// beside its consumer and no routed edge runs through a node's box.
const METRICS = { nodeW: 200, nodeH: 40, rowH: 60, gapMin: 100, track: 10, stub: 10, margin: 20 }

export function nodesCrossedBy(layout, routed, edges) {
  const crossed = []
  for (const [index, points] of routed.routes) {
    const ends = new Set([edges[index].source, edges[index].target])
    for (const [id, at] of routed.nodeAt) {
      if (ends.has(id)) continue
      const box = { x0: at.x, y0: at.y, x1: at.x + METRICS.nodeW, y1: at.y + METRICS.nodeH }
      for (const s of segmentsOf(points)) {
        const hit =
          s.kind === "h"
            ? s.y > box.y0 && s.y < box.y1 && s.x0 < box.x1 && s.x1 > box.x0
            : s.x > box.x0 && s.x < box.x1 && s.y0 < box.y1 && s.y1 > box.y0
        if (hit) {
          crossed.push(`${edges[index].source} -> ${edges[index].target} through ${id}`)
        }
      }
    }
  }
  return crossed
}

describe("layerGraph on the recorded copper-with-gas plan", () => {
  const nodes = edges.flatMap((e) => [e.source, e.target])
  const layout = layerGraph(nodes, edges)
  const routed = routeEdges(layout, edges, METRICS)

  it("places every node once", () => {
    expect(layout.position.size).toBe(new Set(nodes).size)
  })

  it("keeps a supply node next to the machine it feeds", () => {
    const ore = layout.position.get("supply:item_copper_ore")
    const furnace = layout.position.get("furnance_copper_nugget_1")
    expect(furnace.column - ore.column).toBe(1)
  })

  it("never routes an edge through another node", () => {
    expect(nodesCrossedBy(layout, routed, edges)).toEqual([])
  })

  it("gives every node and dummy its own cell", () => {
    const cells = [...layout.position.values(), ...layout.dummies.values()].map(
      (c) => `${c.column}:${c.row}`,
    )
    expect(new Set(cells).size).toBe(cells.length)
  })

  it("routes every edge and reports its crossings", () => {
    expect(routed.routes.size).toBe(edges.filter((e) => e.source !== e.target).length)
    for (const crossing of routed.crossings) {
      expect(routed.routes.has(crossing.edge)).toBe(true)
    }
  })
})
