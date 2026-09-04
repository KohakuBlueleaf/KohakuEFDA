import { pickName } from "@/i18n/names"

export const EDGES = ["N", "E", "S", "W"]
export const STEP = { N: [0, -1], E: [1, 0], S: [0, 1], W: [-1, 0] }
const GLYPH = {
  belt_router: "S",
  pipe_router: "S",
  belt_bridge: "+",
  pipe_bridge: "+",
  belt_control: "F",
  pipe_control: "F",
}
const GEM = {
  iolite: "#5A4FCF",
  ioliteShadow: "#312A7A",
  sapphire: "#0F52BA",
  sapphireLight: "#4F8BE8",
  aquamarine: "#4C9989",
  taaffeite: "#A57EAE",
  amber: "#D4920A",
  coral: "#D46B6B",
  sage: "#5A9E6F",
}

export function palette(dark) {
  return {
    background: dark ? "#0D0F14" : "#EFECE7",
    grid: dark ? "#1A1E26" : "#E0DBD4",
    label: dark ? "#E8E0D8" : "#FFFFFF",
    labelOnBlock: "#FFFFFF",
    belt: GEM.amber,
    pipe: dark ? GEM.sapphireLight : GEM.sapphire,
    beltUnit: "#8B5E00",
    pipeUnit: GEM.sapphire,
    overused: GEM.coral,
    block: GEM.iolite,
    core: GEM.ioliteShadow,
    pylon: GEM.amber,
    coverage: "rgba(212,146,10,0.14)",
    ring: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.06)",
    areaEdge: dark ? "#7FD1FF" : GEM.sapphire,
    fixed: dark ? "#6A645F" : "#8A8480",
    slot: dark ? "rgba(127,209,255,0.35)" : "rgba(15,82,186,0.25)",
    depot: dark ? "#6A645F" : "#8A8480",
    pump: GEM.sapphire,
    treatment: GEM.taaffeite,
    zone: GEM.sage,
    plain: dark ? "#4A4540" : "#A09A92",
    inPort: GEM.aquamarine,
    outPort: GEM.coral,
    selection: GEM.amber,
    channel: dark ? "rgba(255,255,255,0.10)" : "rgba(0,0,0,0.08)",
    badge: dark ? "rgba(13,15,20,0.85)" : "rgba(255,255,255,0.9)",
    badgeText: dark ? "#E8E0D8" : "#2A2724",
    modules: dark ? "#7FD1FF" : GEM.sapphire,
  }
}

export function sizeCanvas(element, width, height) {
  // Backing store at device resolution, CSS size in pixels, drawing in CSS units.
  const ratio = window.devicePixelRatio || 1
  element.width = Math.round(width * ratio)
  element.height = Math.round(height * ratio)
  element.style.width = `${width}px`
  element.style.height = `${height}px`
  const ctx = element.getContext("2d")
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.imageSmoothingEnabled = false
  return ctx
}

export function flowDimensions(frame, catalogue, square) {
  const frameRect = frame?.rect
  const grid = catalogue?.grid ?? square
  if (!frameRect) {
    return grid
  }
  // A packing that overflows the square is still shown whole.
  return [Math.max(grid[0], frameRect[2] + 2), Math.max(grid[1], frameRect[3] + 2)]
}

export function rotateCell(x, y, width, depth, rotation) {
  switch (rotation % 360) {
    case 90:
      return [depth - 1 - y, x]
    case 180:
      return [width - 1 - x, depth - 1 - y]
    case 270:
      return [y, width - 1 - x]
    default:
      return [x, y]
  }
}

export function rotateEdge(edge, rotation) {
  return EDGES[(EDGES.indexOf(edge) + rotation / 90) % 4]
}

export function rotatedSize(width, height, rotation) {
  return rotation % 180 === 0 ? [width, height] : [height, width]
}

export function machineBox(dataset, placed) {
  const machine = dataset.machines[placed.machine_id]
  const [width, depth] = rotatedSize(machine.width, machine.depth, placed.rotation)
  return { x: placed.x, y: placed.y, width, depth, machine }
}

export function machineRole(dataset, machineId) {
  if (machineId === "sp_hub_1") {
    return "core"
  }
  if (dataset.pylons && dataset.pylons[machineId]) {
    return "pylon"
  }
  if (machineId.includes("unloader")) {
    return "unloader"
  }
  if (machineId.includes("loader") || machineId.includes("hongs")) {
    return "loader"
  }
  if (machineId.includes("pump")) {
    return "pump"
  }
  if (dataset.dumps && dataset.dumps[machineId]) {
    return "treatment"
  }
  if (machineId.includes("vaporizer")) {
    return "zone"
  }
  const machine = dataset.machines[machineId]
  return machine?.modes?.length ? "producer" : "plain"
}

export function roleColour(role, p) {
  return (
    {
      core: p.core,
      pylon: p.pylon,
      unloader: p.depot,
      loader: p.depot,
      pump: p.pump,
      treatment: p.treatment,
      zone: p.zone,
      producer: p.block,
      plain: p.plain,
    }[role] ?? p.plain
  )
}

export const ROLE_BADGE = {
  unloader: { glyph: "⇩", key: "fromDepot" },
  loader: { glyph: "⇧", key: "toDepot" },
  pump: { glyph: "≈", key: "fromOutside" },
  treatment: { glyph: "⇣", key: "toOutside" },
}

export function buildIndex(layout, dataset) {
  const ground = new Map()
  const sky = new Map()
  for (const placed of layout.machines) {
    const box = machineBox(dataset, placed)
    for (let dy = 0; dy < box.depth; dy += 1) {
      for (let dx = 0; dx < box.width; dx += 1) {
        const key = `${box.x + dx},${box.y + dy}`
        ground.set(key, { kind: "machine", entity: placed })
        sky.set(key, { kind: "machine", entity: placed })
      }
    }
  }
  for (const unit of layout.units) {
    const spec = dataset.logistics[unit.unit_id]
    const key = `${unit.x},${unit.y}`
    const entry = { kind: "unit", entity: unit }
    if (spec.kind.startsWith("pipe")) {
      sky.set(key, entry)
    }
    ground.set(key, entry)
  }
  for (const segment of layout.segments) {
    const table = segment.kind === "pipe" ? sky : ground
    for (const [x, y] of segment.cells) {
      table.set(`${x},${y}`, { kind: "segment", entity: segment })
    }
  }
  for (const entry of layout.entries ?? []) {
    sky.set(`${entry.x},${entry.y}`, { kind: "entry", entity: entry })
  }
  return { ground, sky }
}

export function drawBackground(ctx, width, height, size, p) {
  ctx.fillStyle = p.background
  ctx.fillRect(0, 0, width * size, height * size)
  if (size < 8) {
    return
  }
  ctx.strokeStyle = p.grid
  ctx.lineWidth = 1
  for (let x = 0; x <= width; x += 1) {
    ctx.beginPath()
    ctx.moveTo(x * size + 0.5, 0)
    ctx.lineTo(x * size + 0.5, height * size)
    ctx.stroke()
  }
  for (let y = 0; y <= height; y += 1) {
    ctx.beginPath()
    ctx.moveTo(0, y * size + 0.5)
    ctx.lineTo(width * size, y * size + 0.5)
    ctx.stroke()
  }
}

export function itemColour(itemId, p, pipe = false) {
  // One stable hue per item id, so an item keeps its colour across every view.
  if (!itemId) {
    return pipe ? p.pipe : p.belt
  }
  let hash = 7
  for (const ch of String(itemId)) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  }
  const hue = hash % 360
  return pipe ? `hsl(${hue} 55% 42%)` : `hsl(${hue} 72% 48%)`
}

export function drawRect(ctx, rect, size, colour) {
  const [x0, y0, x1, y1] = rect
  ctx.strokeStyle = colour
  ctx.lineWidth = 1.5
  ctx.setLineDash([5, 4])
  ctx.strokeRect(x0 * size + 0.5, y0 * size + 0.5, (x1 - x0) * size - 1, (y1 - y0) * size - 1)
  ctx.setLineDash([])
}

export function drawEntries(ctx, entries, dataset, size, p, lang, showLabels = true) {
  // An outside input: an arrow from beyond the edge into its border cell, named by fluid.
  for (const raw of entries) {
    const entry = Array.isArray(raw) ? { id: raw[0], x: raw[1], y: raw[2], edge: raw[3] } : raw
    const [dx, dy] = STEP[entry.edge]
    const colour = itemColour(entry.item_id, p, true)
    const cx = entry.x * size + size / 2
    const cy = entry.y * size + size / 2
    ctx.strokeStyle = colour
    ctx.fillStyle = colour
    ctx.lineWidth = Math.max(2, size * 0.4)
    ctx.beginPath()
    ctx.moveTo(cx + dx * size * 1.4, cy + dy * size * 1.4)
    ctx.lineTo(cx, cy)
    ctx.stroke()
    drawArrow(ctx, cx, cy, [-dx, -dy], size)
    if (showLabels && entry.item_id && size >= 8) {
      const item = dataset.items?.[entry.item_id]
      const text = item ? pickName(item.names, lang) : entry.item_id
      drawBadge(ctx, text, cx + dx * size * 1.6, cy + dy * size * 1.6, size, p, [dx, dy])
    }
  }
}

function drawBadge(ctx, text, x, y, size, p, [dx, dy]) {
  ctx.font = `${Math.max(9, Math.min(13, size))}px sans-serif`
  const width = ctx.measureText(text).width + 8
  const height = Math.max(12, Math.min(16, size + 2))
  const left = dx < 0 ? x - width : dx > 0 ? x : x - width / 2
  const top = dy < 0 ? y - height : dy > 0 ? y : y - height / 2
  ctx.fillStyle = p.badge
  ctx.beginPath()
  ctx.roundRect(left, top, width, height, 3)
  ctx.fill()
  ctx.fillStyle = p.badgeText
  ctx.textAlign = "left"
  ctx.textBaseline = "middle"
  ctx.fillText(text, left + 4, top + height / 2)
}

function drawItemLabels(ctx, layout, dataset, size, p, lang, showGround, showSky) {
  // One name per wire, on its longest piece, at that piece's middle cell.
  const best = new Map()
  for (const segment of layout.segments) {
    if (!segment.item_id || segment.cells.length < 2) {
      continue
    }
    if ((segment.kind === "belt" && !showGround) || (segment.kind === "pipe" && !showSky)) {
      continue
    }
    const wire = segment.id.split(":")[0]
    const current = best.get(wire)
    if (!current || current.cells.length < segment.cells.length) {
      best.set(wire, segment)
    }
  }
  for (const segment of best.values()) {
    const [x, y] = segment.cells[Math.floor(segment.cells.length / 2)]
    const item = dataset.items?.[segment.item_id]
    const text = item ? pickName(item.names, lang) : segment.item_id
    drawBadge(ctx, text, x * size + size / 2, y * size + size / 2, size, p, [0, 0])
  }
}

export function drawLayout(ctx, layout, dataset, size, p, options = {}) {
  const {
    showGround = true,
    showSky = true,
    showLabels = true,
    showItems = true,
    showModules = false,
    showBadges = true,
    showCoverage = false,
    highlight = "",
    lang = "en",
  } = options
  if (layout.area) {
    drawArea(ctx, [layout.width, layout.height], layout.area, size, p)
  }
  const pylons = layout.machines.filter((m) => dataset.pylons?.[m.machine_id])
  if (pylons.length) {
    const reach = dataset.pylons[pylons[0].machine_id].reach
    drawPylons(
      ctx,
      pylons.map((m) => [m.x, m.y]),
      reach,
      size,
      p,
      { showCoverage },
    )
  }
  for (const placed of layout.machines) {
    if (placed.machine_id === "vaporizer_1") {
      drawZone(ctx, placed.x, placed.y, dataset.machines[placed.machine_id].width, size, p)
    }
    drawMachine(ctx, dataset, placed, size, p, showLabels, lang)
  }
  if (showGround) {
    for (const segment of layout.segments.filter((s) => s.kind === "belt")) {
      const colour = showItems ? itemColour(segment.item_id, p) : p.belt
      drawPath(ctx, segment.cells, size, colour, 0.32, segment.heading)
    }
  }
  if (showSky) {
    for (const segment of layout.segments.filter((s) => s.kind === "pipe")) {
      const colour = showItems ? itemColour(segment.item_id, p, true) : p.pipe
      drawPath(ctx, segment.cells, size, colour, 0.5, segment.heading, true)
    }
  }
  drawEntries(ctx, layout.entries ?? [], dataset, size, p, lang, showItems)
  for (const unit of layout.units ?? []) {
    const spec = dataset.logistics[unit.unit_id]
    const pipe = spec.kind.startsWith("pipe")
    if ((pipe && !showSky) || (!pipe && !showGround)) {
      continue
    }
    ctx.fillStyle = pipe ? p.pipeUnit : p.beltUnit
    ctx.fillRect(unit.x * size + 1, unit.y * size + 1, size - 2, size - 2)
    if (size >= 10) {
      ctx.fillStyle = "#ffffff"
      ctx.font = `${Math.max(8, size - 5)}px sans-serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "middle"
      ctx.fillText(GLYPH[spec.kind] ?? "?", unit.x * size + size / 2, unit.y * size + size / 2)
    }
  }
  if (showBadges && size >= 8) {
    drawBadges(ctx, layout, dataset, size, p)
  }
  if (showItems && size >= 8) {
    drawItemLabels(ctx, layout, dataset, size, p, lang, showGround, showSky)
  }
  if (showModules) {
    for (const module of layout.modules ?? []) {
      const active = module.id === highlight
      ctx.strokeStyle = active ? p.selection : p.modules
      ctx.lineWidth = active ? 3 : 1
      ctx.setLineDash([6, 4])
      ctx.strokeRect(module.x * size, module.y * size, module.width * size, module.height * size)
      ctx.setLineDash([])
      ctx.fillStyle = ctx.strokeStyle
      ctx.font = "12px sans-serif"
      ctx.textAlign = "left"
      ctx.textBaseline = "top"
      ctx.fillText(module.id, module.x * size + 3, module.y * size + 3)
    }
  }
}

export function drawMachine(ctx, dataset, placed, size, p, showLabels, lang, role = null) {
  const box = machineBox(dataset, placed)
  ctx.fillStyle = roleColour(role ?? machineRole(dataset, placed.machine_id), p)
  ctx.fillRect(box.x * size + 1, box.y * size + 1, box.width * size - 2, box.depth * size - 2)
  for (const port of box.machine.ports) {
    const [px, py] = rotateCell(
      port.x,
      port.y,
      box.machine.width,
      box.machine.depth,
      placed.rotation,
    )
    const edge = rotateEdge(port.edge, placed.rotation)
    drawPort(ctx, box.x + px, box.y + py, edge, port.direction === "in", size, p)
  }
  if (showLabels && size >= 10) {
    const label = pickName(box.machine.names, lang)
    ctx.fillStyle = p.labelOnBlock
    ctx.font = `${Math.max(9, size - 4)}px sans-serif`
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText(
      label,
      box.x * size + (box.width * size) / 2,
      box.y * size + (box.depth * size) / 2,
      box.width * size - 4,
    )
  }
}

export function drawBadges(ctx, layout, dataset, size, p) {
  for (const placed of layout.machines) {
    const badge = ROLE_BADGE[machineRole(dataset, placed.machine_id)]
    if (!badge) {
      continue
    }
    const r = Math.max(6, size * 0.6)
    const x = placed.x * size + 2
    const y = placed.y * size + 2
    ctx.fillStyle = p.badge
    ctx.beginPath()
    ctx.roundRect(x, y, r * 1.6, r * 1.6, 3)
    ctx.fill()
    ctx.fillStyle = p.badgeText
    ctx.font = `bold ${Math.max(8, r)}px sans-serif`
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText(badge.glyph, x + r * 0.8, y + r * 0.8)
  }
}

export function drawPort(ctx, x, y, edge, inward, size, p) {
  const [dx, dy] = STEP[edge]
  const cx = x * size + size / 2 + (dx * size) / 2
  const cy = y * size + size / 2 + (dy * size) / 2
  const r = Math.max(2, size / 5)
  ctx.fillStyle = inward ? p.inPort : p.outPort
  ctx.beginPath()
  ctx.arc(cx - (dx * r) / 2, cy - (dy * r) / 2, r, 0, Math.PI * 2)
  ctx.fill()
}

export function drawPath(ctx, cells, size, colour, widthFactor, heading = null, dashed = false) {
  if (!cells.length) {
    return
  }
  ctx.strokeStyle = colour
  ctx.fillStyle = colour
  ctx.lineWidth = Math.max(2, size * widthFactor)
  ctx.lineCap = "round"
  ctx.lineJoin = "round"
  ctx.setLineDash(dashed ? [Math.max(3, size * 0.55), Math.max(2, size * 0.35)] : [])
  ctx.beginPath()
  cells.forEach(([x, y], position) => {
    const cx = x * size + size / 2
    const cy = y * size + size / 2
    if (position === 0) {
      ctx.moveTo(cx, cy)
    } else {
      ctx.lineTo(cx, cy)
    }
  })
  ctx.stroke()
  ctx.setLineDash([])
  const last = cells[cells.length - 1]
  let step = null
  if (heading) {
    step = STEP[heading]
  } else if (cells.length >= 2) {
    const before = cells[cells.length - 2]
    step = [last[0] - before[0], last[1] - before[1]]
  }
  if (step) {
    drawArrow(ctx, last[0] * size + size / 2, last[1] * size + size / 2, step, size)
  }
}

function drawArrow(ctx, cx, cy, [dx, dy], size) {
  const r = Math.max(3, size * 0.35)
  ctx.beginPath()
  ctx.moveTo(cx + dx * r, cy + dy * r)
  ctx.lineTo(cx - dy * r * 0.7 - dx * r * 0.4, cy + dx * r * 0.7 - dy * r * 0.4)
  ctx.lineTo(cx + dy * r * 0.7 - dx * r * 0.4, cy - dx * r * 0.7 - dy * r * 0.4)
  ctx.closePath()
  ctx.fill()
}

export function drawMarks(ctx, cells, size, colour) {
  ctx.strokeStyle = colour
  ctx.lineWidth = Math.max(1.5, size / 6)
  for (const [x, y] of cells) {
    ctx.strokeRect(x * size + 1.5, y * size + 1.5, size - 3, size - 3)
  }
}

export const ZONE_SIDE = 13
export const PYLON_SIZE = 2
const KIND_ROLE = {
  core: "core",
  depot: "loader",
  unloader: "unloader",
  loader: "loader",
  entry: "pump",
  dump: "treatment",
  zone: "zone",
  recipe: "producer",
}

export function drawArea(ctx, grid, area, size, p) {
  // The ring around the Core AIC Area is shaded; the area itself keeps the background.
  const [width, height] = grid
  const [x0, y0, x1, y1] = area
  ctx.fillStyle = p.ring
  ctx.fillRect(0, 0, width * size, y0 * size)
  ctx.fillRect(0, y1 * size, width * size, (height - y1) * size)
  ctx.fillRect(0, y0 * size, x0 * size, (y1 - y0) * size)
  ctx.fillRect(x1 * size, y0 * size, (width - x1) * size, (y1 - y0) * size)
  ctx.strokeStyle = p.areaEdge
  ctx.lineWidth = 2
  ctx.strokeRect(x0 * size + 1, y0 * size + 1, (x1 - x0) * size - 2, (y1 - y0) * size - 2)
}

export function drawCells(ctx, cells, size, colour) {
  ctx.fillStyle = colour
  for (const [x, y] of cells) {
    ctx.fillRect(x * size + 1, y * size + 1, size - 2, size - 2)
  }
}

export function drawPylons(ctx, pylons, reach, size, p, options = {}) {
  const { showCoverage = true } = options
  for (const [x, y] of pylons) {
    if (showCoverage) {
      ctx.fillStyle = p.coverage
      ctx.fillRect(
        (x - reach) * size,
        (y - reach) * size,
        (PYLON_SIZE + 2 * reach) * size,
        (PYLON_SIZE + 2 * reach) * size,
      )
    }
    ctx.fillStyle = p.pylon
    ctx.fillRect(x * size + 1, y * size + 1, PYLON_SIZE * size - 2, PYLON_SIZE * size - 2)
  }
}

export function drawZone(ctx, x, y, footprint, size, p) {
  const half = Math.floor(ZONE_SIDE / 2)
  const cx = x + Math.floor(footprint / 2)
  const cy = y + Math.floor(footprint / 2)
  ctx.strokeStyle = p.zone
  ctx.lineWidth = 1.5
  ctx.setLineDash([4, 3])
  ctx.strokeRect(
    (cx - half) * size + 0.5,
    (cy - half) * size + 0.5,
    ZONE_SIDE * size - 1,
    ZONE_SIDE * size - 1,
  )
  ctx.setLineDash([])
}

export function blockMachines(dataset, block, x, y, rotation) {
  // Every machine of a block as a placed entity in grid coordinates.
  return block.machines.map((placed) => {
    const machine = dataset.machines[placed.machine_id]
    const [w, d] = rotatedSize(machine.width, machine.depth, placed.rotation)
    const corners = [
      rotateCell(placed.x, placed.y, block.width, block.height, rotation),
      rotateCell(placed.x + w - 1, placed.y + d - 1, block.width, block.height, rotation),
    ]
    return {
      ...placed,
      x: x + Math.min(corners[0][0], corners[1][0]),
      y: y + Math.min(corners[0][1], corners[1][1]),
      rotation: (placed.rotation + rotation) % 360,
    }
  })
}

export function drawBlocks(ctx, dataset, catalogue, positions, size, p, options = {}) {
  const { showLabels = true, lang = "en" } = options
  const byId = new Map(catalogue.map((block) => [block.id, block]))
  for (const [id, x, y, rotation] of positions) {
    const block = byId.get(id)
    if (!block) {
      continue
    }
    for (const placed of blockMachines(dataset, block, x, y, rotation)) {
      if (placed.machine_id === "vaporizer_1") {
        drawZone(ctx, placed.x, placed.y, dataset.machines[placed.machine_id].width, size, p)
      }
      const role = placed.recipe_id ? "producer" : KIND_ROLE[block.kind]
      drawMachine(ctx, dataset, placed, size, p, showLabels, lang, role)
    }
    for (const pin of block.pins) {
      const [px, py] = rotateCell(pin.x, pin.y, block.width, block.height, rotation)
      const edge = rotateEdge(pin.edge, rotation)
      const [dx, dy] = STEP[edge]
      const cx = (x + px) * size + size / 2 + (dx * size) / 2
      const cy = (y + py) * size + size / 2 + (dy * size) / 2
      const r = Math.max(2, size / 4)
      ctx.beginPath()
      ctx.arc(cx - (dx * r) / 2, cy - (dy * r) / 2, r, 0, Math.PI * 2)
      const colour = pin.kind === "pipe" ? p.pipe : p.belt
      if (pin.direction === "in") {
        ctx.fillStyle = colour
        ctx.fill()
      } else {
        ctx.strokeStyle = colour
        ctx.lineWidth = 2
        ctx.stroke()
      }
    }
  }
}
