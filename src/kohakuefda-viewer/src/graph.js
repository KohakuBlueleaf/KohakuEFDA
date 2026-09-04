// Sugiyama drawing of a flow graph with cycles: back edges cut, longest-path ranks, dummies
// on long edges, barycenter sweeps, one orthogonal track per edge and gap, crossings marked.

const SWEEPS = 4

export function backEdges(nodes, edges) {
  const out = new Map(nodes.map((id) => [id, []]))
  for (const [index, edge] of edges.entries()) {
    if (edge.source !== edge.target) {
      out.get(edge.source).push({ target: edge.target, index })
    }
  }
  const state = new Map(nodes.map((id) => [id, 0]))
  const back = new Set()
  function visit(id) {
    state.set(id, 1)
    for (const { target, index } of out.get(id)) {
      const seen = state.get(target)
      if (seen === 1) {
        back.add(index)
      } else if (seen === 0) {
        visit(target)
      }
    }
    state.set(id, 2)
  }
  for (const id of nodes) {
    if (state.get(id) === 0) {
      visit(id)
    }
  }
  return back
}

function rankNodes(ids, forward) {
  const incoming = new Map(ids.map((id) => [id, 0]))
  const successors = new Map(ids.map((id) => [id, []]))
  for (const edge of forward) {
    incoming.set(edge.target, incoming.get(edge.target) + 1)
    successors.get(edge.source).push(edge.target)
  }
  const rank = new Map(ids.map((id) => [id, 0]))
  const queue = ids.filter((id) => incoming.get(id) === 0)
  const sources = new Set(queue)
  while (queue.length) {
    const id = queue.shift()
    for (const next of successors.get(id)) {
      rank.set(next, Math.max(rank.get(next), rank.get(id) + 1))
      incoming.set(next, incoming.get(next) - 1)
      if (incoming.get(next) === 0) {
        queue.push(next)
      }
    }
  }
  for (const id of sources) {
    const fed = successors.get(id)
    if (fed.length) {
      rank.set(id, Math.min(...fed.map((next) => rank.get(next))) - 1)
    }
  }
  const lowest = Math.min(0, ...rank.values())
  for (const id of ids) {
    rank.set(id, rank.get(id) - lowest)
  }
  return rank
}

function mean(values, fallback) {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : fallback
}

function sweep(columns, links, order, direction) {
  // One barycenter pass: sort every column by the mean row of its neighbours in the column
  // the pass comes from; a node without neighbours keeps its place.
  const keys = [...columns.keys()].sort((a, b) => (direction > 0 ? a - b : b - a))
  for (const column of keys) {
    const members = columns.get(column)
    const rows = new Map(members.map((id, row) => [id, row]))
    const keyed = members.map((id) => {
      const beside = links
        .filter((link) => (direction > 0 ? link.target === id : link.source === id))
        .map((link) => (direction > 0 ? link.source : link.target))
        .filter((other) => order.has(other))
        .map((other) => order.get(other))
      return { id, mean: mean(beside, rows.get(id)), given: rows.get(id) }
    })
    keyed.sort((a, b) => a.mean - b.mean || a.given - b.given)
    columns.set(
      column,
      keyed.map(({ id }) => id),
    )
    keyed.forEach(({ id }, row) => order.set(id, row))
  }
}

export function layerGraph(nodes, edges) {
  const ids = [...new Set(nodes)]
  const back = backEdges(ids, edges)
  const forward = edges
    .map((edge, index) => ({ ...edge, index }))
    .filter((edge) => edge.source !== edge.target && !back.has(edge.index))
  const rank = rankNodes(ids, forward)
  const columns = new Map()
  const place = (id, column) => {
    if (!columns.has(column)) {
      columns.set(column, [])
    }
    columns.get(column).push(id)
  }
  for (const id of ids) {
    place(id, rank.get(id))
  }
  // Long edges become chains through one dummy per intermediate column.
  const chains = new Map()
  const links = []
  const dummies = new Set()
  for (const edge of forward) {
    const from = rank.get(edge.source)
    const to = rank.get(edge.target)
    const path = [edge.source]
    for (let column = from + 1; column < to; column += 1) {
      const dummy = `dummy:${edge.index}:${column}`
      dummies.add(dummy)
      rank.set(dummy, column)
      place(dummy, column)
      path.push(dummy)
    }
    path.push(edge.target)
    chains.set(edge.index, path)
    for (let n = 0; n + 1 < path.length; n += 1) {
      links.push({ source: path[n], target: path[n + 1] })
    }
  }
  const order = new Map()
  for (const members of columns.values()) {
    members.forEach((id, row) => order.set(id, row))
  }
  for (let round = 0; round < SWEEPS; round += 1) {
    sweep(columns, links, order, 1)
    sweep(columns, links, order, -1)
  }
  sweep(columns, links, order, 1)
  const position = new Map()
  const dummyPosition = new Map()
  for (const [column, members] of columns) {
    members.forEach((id, row) => {
      ;(dummies.has(id) ? dummyPosition : position).set(id, { column, row })
    })
  }
  return {
    position,
    dummies: dummyPosition,
    chains,
    back,
    columns: columns.size ? Math.max(...columns.keys()) + 1 : 0,
    rows: Math.max(0, ...[...columns.values()].map((members) => members.length)),
  }
}

const OUT_BAND = [0.12, 0.48]
const IN_BAND = [0.52, 0.88]

function trackKey(sub) {
  // Downward edges left by descending start, upward ones by ascending: only edges whose
  // order flips still cross, and those cross under any track order.
  return sub.y1 >= sub.y0 ? [0, -sub.y0, -sub.y1] : [1, sub.y0, sub.y1]
}

function slotY(nodeY, nodeH, band, index, count) {
  return nodeY + nodeH * (band[0] + ((band[1] - band[0]) * (index + 1)) / (count + 1))
}

function compareKeys(a, b) {
  for (let n = 0; n < a.length; n += 1) {
    if (a[n] !== b[n]) {
      return a[n] - b[n]
    }
  }
  return 0
}

function assignTracks(subs) {
  // Every gap: its sub-edges sorted by the key, one track each, left to right.
  const byGap = new Map()
  for (const sub of subs) {
    if (!byGap.has(sub.gap)) {
      byGap.set(sub.gap, [])
    }
    byGap.get(sub.gap).push(sub)
  }
  const tracks = new Map()
  for (const [gap, members] of byGap) {
    const sorted = [...members].sort((a, b) => compareKeys(trackKey(a), trackKey(b)))
    sorted.forEach((sub, index) => tracks.set(sub, index))
    byGap.set(gap, sorted.length)
  }
  return { tracks, counts: byGap }
}

export function routeEdges(layout, edges, metrics) {
  // Node anchors, one orthogonal polyline per edge (back edges return under the graph),
  // the crossings between them, and the drawing's size.
  const { nodeW, nodeH, rowH, gapMin, track, stub, margin } = metrics
  const rowOf = new Map([...layout.position, ...layout.dummies].map(([id, p]) => [id, p.row]))
  const columnOf = new Map([...layout.position, ...layout.dummies].map(([id, p]) => [id, p.column]))
  const nodeY = (id) => margin + rowOf.get(id) * rowH
  const bottomY = (lane) => margin + layout.rows * rowH + lane * track
  // Every link of every chain, with the row each end leaves from or arrives at.
  const links = []
  const bottomLanes = []
  edges.forEach((edge, index) => {
    if (edge.source === edge.target) {
      return
    }
    if (layout.back.has(index)) {
      const lane = bottomLanes.length
      bottomLanes.push(index)
      links.push({ edge: index, from: edge.source, to: `lane:${lane}`, lane, part: "drop" })
      links.push({ edge: index, from: `lane:${lane}`, to: edge.target, lane, part: "rise" })
      return
    }
    const path = layout.chains.get(index)
    for (let n = 0; n + 1 < path.length; n += 1) {
      links.push({ edge: index, from: path[n], to: path[n + 1], part: n })
    }
  })
  // A real node hands out one y per leaving link in its upper band and one per arriving
  // link in its lower band, ordered by the far end's row; a dummy or a lane is one y.
  const yAt = (id, lane) => (id.startsWith("lane:") ? bottomY(lane) : nodeY(id) + nodeH / 2)
  const farRow = (id, lane) => (id.startsWith("lane:") ? layout.rows + lane : rowOf.get(id))
  const outY = new Map()
  const inY = new Map()
  for (const id of layout.position.keys()) {
    const leaving = links
      .filter((l) => l.from === id)
      .sort((a, b) => farRow(a.to, a.lane) - farRow(b.to, b.lane))
    leaving.forEach((l, k) => outY.set(l, slotY(nodeY(id), nodeH, OUT_BAND, k, leaving.length)))
    const arriving = links
      .filter((l) => l.to === id)
      .sort((a, b) => farRow(a.from, a.lane) - farRow(b.from, b.lane))
    arriving.forEach((l, k) => inY.set(l, slotY(nodeY(id), nodeH, IN_BAND, k, arriving.length)))
  }
  const subs = links.map((link) => ({
    ...link,
    gap: link.part === "rise" ? columnOf.get(link.to) - 1 : columnOf.get(link.from),
    y0: outY.get(link) ?? yAt(link.from, link.lane),
    y1: inY.get(link) ?? yAt(link.to, link.lane),
  }))
  const { tracks, counts } = assignTracks(subs)
  const columnX = []
  const gapWidth = []
  let x = margin
  for (let column = 0; column < layout.columns; column += 1) {
    columnX.push(x)
    const width = Math.max(gapMin, (counts.get(column) ?? 0) * track + 2 * stub)
    gapWidth.push(width)
    x += nodeW + width
  }
  const leftGapX = (gap) => (gap < 0 ? margin - gapMin : columnX[gap] + nodeW)
  const trackX = (sub) => leftGapX(sub.gap) + stub + tracks.get(sub) * track
  const sideX = (id, entering) => columnX[columnOf.get(id)] + (entering ? 0 : nodeW)
  const routes = new Map()
  edges.forEach((edge, index) => {
    if (edge.source === edge.target) {
      return
    }
    const mine = subs.filter((sub) => sub.edge === index)
    const points = []
    if (layout.back.has(index)) {
      const [drop, rise] = mine
      const xa = trackX(drop)
      const xb = trackX(rise)
      points.push(
        { x: sideX(edge.source, false), y: drop.y0 },
        { x: xa, y: drop.y0 },
        { x: xa, y: drop.y1 },
        { x: xb, y: rise.y0 },
        { x: xb, y: rise.y1 },
        { x: sideX(edge.target, true), y: rise.y1 },
      )
    } else {
      points.push({ x: sideX(edge.source, false), y: mine[0].y0 })
      mine.forEach((sub, n) => {
        const tx = trackX(sub)
        points.push({ x: tx, y: sub.y0 })
        if (sub.y1 !== sub.y0) {
          points.push({ x: tx, y: sub.y1 })
        }
        const last = n + 1 === mine.length
        points.push({ x: sideX(sub.to, true), y: sub.y1 })
        if (!last) {
          points.push({ x: sideX(sub.to, false), y: sub.y1 })
        }
      })
    }
    routes.set(index, dedupe(points))
  })
  const crossings = findCrossings(routes)
  const width = (columnX.at(-1) ?? margin) + nodeW + margin
  const height = margin + layout.rows * rowH + bottomLanes.length * track + margin
  const nodeAt = new Map()
  for (const [id, { column, row }] of layout.position) {
    nodeAt.set(id, { x: columnX[column], y: margin + row * rowH })
  }
  return { routes, crossings, width, height, nodeAt, columnX, gapWidth }
}

function dedupe(points) {
  const out = []
  for (const point of points) {
    const last = out.at(-1)
    if (!last || last.x !== point.x || last.y !== point.y) {
      out.push(point)
    }
  }
  return out
}

export function segmentsOf(points) {
  const out = []
  for (let n = 0; n + 1 < points.length; n += 1) {
    const a = points[n]
    const b = points[n + 1]
    out.push(
      a.y === b.y
        ? { kind: "h", y: a.y, x0: Math.min(a.x, b.x), x1: Math.max(a.x, b.x), index: n }
        : { kind: "v", x: a.x, y0: Math.min(a.y, b.y), y1: Math.max(a.y, b.y), index: n },
    )
  }
  return out
}

export function findCrossings(routes) {
  // Every point where a horizontal run of one edge meets a vertical run of another.
  const horizontals = []
  const verticals = []
  for (const [edge, points] of routes) {
    for (const segment of segmentsOf(points)) {
      ;(segment.kind === "h" ? horizontals : verticals).push({ ...segment, edge })
    }
  }
  const out = []
  for (const h of horizontals) {
    for (const v of verticals) {
      if (h.edge !== v.edge && h.x0 < v.x && v.x < h.x1 && v.y0 < h.y && h.y < v.y1) {
        out.push({ x: v.x, y: h.y, edge: h.edge, segment: h.index })
      }
    }
  }
  return out
}

export function pathWithJumps(points, crossings, radius) {
  // The SVG path of a polyline whose horizontal runs hop over the crossings on them.
  let d = `M ${points[0].x} ${points[0].y}`
  for (let n = 0; n + 1 < points.length; n += 1) {
    const a = points[n]
    const b = points[n + 1]
    if (a.y !== b.y) {
      d += ` L ${b.x} ${b.y}`
      continue
    }
    const step = b.x >= a.x ? 1 : -1
    const hops = crossings
      .filter((c) => c.segment === n)
      .map((c) => c.x)
      .sort((p, q) => (p - q) * step)
    for (const hop of hops) {
      d += ` L ${hop - step * radius} ${a.y}`
      d += ` A ${radius} ${radius} 0 0 ${step > 0 ? 1 : 0} ${hop + step * radius} ${a.y}`
    }
    d += ` L ${b.x} ${b.y}`
  }
  return d
}

export function labelAnchor(points, minRun) {
  // Where an edge's label goes: the middle of its longest horizontal run when that run is
  // at least ``minRun`` wide, else beside the middle of its longest vertical run.
  let best = null
  for (const segment of segmentsOf(points)) {
    const length = segment.kind === "h" ? segment.x1 - segment.x0 : segment.y1 - segment.y0
    if (segment.kind === "h" && (!best || best.kind !== "h" || length > best.length)) {
      best = { ...segment, length }
    } else if (segment.kind === "v" && (!best || (best.kind === "v" && length > best.length))) {
      best = { ...segment, length }
    }
  }
  if (!best) {
    return { x: points[0].x, y: points[0].y, along: "h" }
  }
  if (best.kind === "h" && best.length >= minRun) {
    return { x: (best.x0 + best.x1) / 2, y: best.y, along: "h" }
  }
  const vertical = segmentsOf(points)
    .filter((s) => s.kind === "v")
    .sort((a, b) => b.y1 - b.y0 - (a.y1 - a.y0))[0]
  if (vertical) {
    return { x: vertical.x, y: (vertical.y0 + vertical.y1) / 2, along: "v" }
  }
  return { x: (best.x0 + best.x1) / 2, y: best.y, along: "h" }
}
