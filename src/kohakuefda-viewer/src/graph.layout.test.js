import { describe, expect, it } from "vitest"
import { layerGraph } from "./graph"

// Two ores refined by two different recipes must land on two distinct nodes.
describe("layerGraph on a plan with two refining recipes", () => {
  it("gives every node its own cell", () => {
    const edges = [
      { source: "supply:item_copper_ore", target: "furnance_copper_nugget_1" },
      { source: "supply:item_iron_ore", target: "furnance_iron_nugget_1" },
      { source: "furnance_copper_nugget_1", target: "component_copper_cmpt_1" },
      { source: "furnance_iron_nugget_1", target: "grinder_iron_powder_1" },
      { source: "grinder_iron_powder_1", target: "pool_copper_enr_1" },
      { source: "component_copper_cmpt_1", target: "target:item_copper_cmpt" },
    ]
    const nodes = edges.flatMap((e) => [e.source, e.target])
    const layout = layerGraph(nodes, edges)
    const cells = new Set()
    for (const [, { column, row }] of layout.position) {
      const cell = `${column}:${row}`
      expect(cells.has(cell)).toBe(false)
      cells.add(cell)
    }
    expect(layout.position.get("furnance_copper_nugget_1").column).toBe(1)
    expect(layout.position.get("furnance_iron_nugget_1").column).toBe(1)
    expect(layout.position.size).toBe(8)
  })
})
