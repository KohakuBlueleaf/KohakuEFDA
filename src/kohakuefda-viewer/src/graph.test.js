import { describe, expect, it } from "vitest"
import { backEdges, layerGraph } from "./graph"

describe("layerGraph", () => {
  it("ranks a chain by longest path", () => {
    const layout = layerGraph(
      ["a", "b", "c"],
      [
        { source: "a", target: "b" },
        { source: "b", target: "c" },
        { source: "a", target: "c" },
      ],
    )
    expect(layout.position.get("a").column).toBe(0)
    expect(layout.position.get("b").column).toBe(1)
    expect(layout.position.get("c").column).toBe(2)
    expect(layout.columns).toBe(3)
  })

  it("keeps a seed loop and a self loop within a few columns", () => {
    const nodes = ["supply", "planter", "collector", "grinder", "target"]
    const edges = [
      { source: "supply", target: "planter" },
      { source: "planter", target: "collector" },
      { source: "collector", target: "planter" },
      { source: "planter", target: "grinder" },
      { source: "grinder", target: "target" },
      { source: "grinder", target: "grinder" },
    ]
    const layout = layerGraph(nodes, edges)
    expect(layout.columns).toBeLessThanOrEqual(4)
    expect(layout.position.get("grinder").column).toBe(2)
    expect(layout.position.get("target").column).toBe(3)
    expect(backEdges(nodes, edges).size).toBe(1)
    for (const id of nodes) {
      expect(layout.position.has(id)).toBe(true)
    }
  })

  it("orders a column by its predecessors", () => {
    const layout = layerGraph(
      ["top", "bottom", "x", "y"],
      [
        { source: "top", target: "y" },
        { source: "bottom", target: "x" },
      ],
    )
    expect(layout.position.get("top").row).toBe(0)
    expect(layout.position.get("bottom").row).toBe(1)
    expect(layout.position.get("y").row).toBe(0)
    expect(layout.position.get("x").row).toBe(1)
  })
})
