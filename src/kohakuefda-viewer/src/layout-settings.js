export const PRIMARY = [
  "solver",
  "seconds",
  "max_actions",
  "backend",
  "seed",
  "until_budget",
  "workers",
  "construction_steps",
  "improvement_steps",
  "spread_attempts",
  "attempts",
]
const INTEGERS = new Set(["seed", "workers", "max_actions", "frame_every", "route_iterations"])
const GROUPS = [
  [
    "construction",
    /^(construction_|frontier_|insertion_|local_repair_|candidates$|gap|refill|restart|repair_threshold|radius|neighbor|expand|pressure|failure_pressure|repair_pressure|replace_equal|jitter|closed_cost|center_weight|corner_weight|depot_|flow_order|spread_)/,
  ],
  [
    "improvement",
    /^(improvement_|move_|cluster_|compaction_|compact_|pull_|wire_tiebreak|repack_|shrink_)/,
  ],
  ["annealing", /temperature|cooling/],
  [
    "routing",
    /^(repair_actions|repair_route_calls|route_|present_|turn_cost|bridge_cost|history_cost)/,
  ],
  ["space", /^(w_|entry_sides|pylon)/],
]

export function solverEntry(solvers, name) {
  return solvers.find((entry) => entry.name === name)
}

export function parseOptions(text) {
  const value = JSON.parse(text || "{}")
  if (value === null || Array.isArray(value) || typeof value !== "object") {
    throw new Error("solver_options must be a JSON object")
  }
  return value
}

export function optionValues(entry, draft) {
  const values = { ...entry.defaults }
  for (const key of Object.keys(values)) {
    if (key in draft) values[key] = draft[key]
  }
  return { ...values, ...parseOptions(draft.solver_options) }
}

export function layoutFields(defaults, solvers, name) {
  const entry = solverEntry(solvers, name)
  if (!entry) return []
  const solverKeys = new Set(solvers.flatMap((item) => Object.keys(item.defaults)))
  const shared = Object.entries(defaults)
    .filter(([key]) => key !== "solver_options" && !solverKeys.has(key))
    .filter(([key]) => key !== "workers" || entry.parallel === true)
    .map(([key, value]) => ({
      key,
      scope: "stage",
      default: value,
      type: typeof value === "string" ? "str" : INTEGERS.has(key) ? "int" : "float",
    }))
  const options = Object.entries(entry.defaults).map(([key, value]) => ({
    key,
    scope: "solver",
    default: value,
    type:
      entry.parameter_types?.[key] ??
      (typeof value === "boolean"
        ? "bool"
        : typeof value === "string"
          ? "str"
          : Number.isInteger(value)
            ? "int"
            : "float"),
  }))
  return [...shared, ...options]
}

export function fieldGroups(fields) {
  const groups = new Map()
  for (const field of fields.filter((f) => !PRIMARY.includes(f.key))) {
    const key = /temperature|cooling/.test(field.key)
      ? "annealing"
      : (GROUPS.find(([, pattern]) => pattern.test(field.key))?.[0] ?? "other")
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(field)
  }
  return [...groups].map(([key, fields]) => ({ key, fields }))
}

function typed(field, value) {
  if (field.type === "bool") {
    if (typeof value !== "boolean") throw new Error(`${field.key}: expected a boolean`)
    return value
  }
  if (field.type === "str") return String(value)
  if (value === "" || value === null || typeof value === "boolean")
    throw new Error(`${field.key}: expected a number`)
  const number = Number(value)
  if (
    !Number.isFinite(number) ||
    (number < 0 && field.key !== "seed") ||
    (field.type === "int" && !Number.isInteger(number))
  ) {
    throw new Error(
      `${field.key}: expected a finite ${field.type === "int" ? "integer" : "number"}${field.key === "seed" ? "" : " >= 0"}`,
    )
  }
  return number
}

export function collectLayout(defaults, solvers, draft) {
  const entry = solverEntry(solvers, draft.solver)
  if (!entry) throw new Error(`Unknown solver: ${draft.solver}`)
  const options = optionValues(entry, draft)
  for (const key of Object.keys(options)) {
    if (!(key in entry.defaults)) throw new Error(`Unknown ${entry.name} option: ${key}`)
  }
  const out = {},
    solver = {}
  for (const field of layoutFields(defaults, solvers, draft.solver)) {
    const target = field.scope === "solver" ? solver : out
    target[field.key] = typed(
      field,
      field.scope === "solver" ? options[field.key] : (draft[field.key] ?? field.default),
    )
  }
  if (!entry.parallel) out.workers = 1
  out.solver_options = JSON.stringify(solver)
  return out
}

export function effectiveLimits(payload) {
  const options = parseOptions(payload.solver_options)
  const global = Number(payload.seconds) > 0 || Number(payload.max_actions) > 0
  return { global, untilBudget: options.until_budget === true && global, options }
}

export function layoutOutcome(state, frames = []) {
  if (state?.outcome) return state.outcome
  if (!state || ["idle", "running", "queued"].includes(state.status)) return null
  const frame = frames.findLast((f) => f?.kind === "final")
  if (!frame) return null
  return (
    frame.outcome ?? {
      status: frame.status ?? "completed",
      routed: frame.evidence?.routed ?? frame.clean ?? frame.fits,
      placed: frame.placed,
      total: frame.total,
      elapsed: frame.elapsed ?? state.finished - state.started,
      settings: { runtime: state.params, solver_settings: {} },
    }
  )
}

export function layoutStatus(state, frames = []) {
  if (!state) return "idle"
  const outcome = layoutOutcome(state, frames)
  return state.status === "done" && outcome?.routed === false ? "incomplete" : state.status
}
