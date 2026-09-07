const PHASES = { build: "construction", improve: "improvement", final: "final" }

export function progressFrames(frames) {
  return frames.filter(
    (frame) => frame && frame.kind !== "catalogue" && (Array.isArray(frame.blocks) || frame.layout),
  )
}

export function frameSpace(frame, catalogue, fallback = [50, 50]) {
  const grid =
    frame?.grid ??
    (frame?.layout ? [frame.layout.width, frame.layout.height] : null) ??
    catalogue?.grid ??
    fallback
  const area = frame?.area ?? frame?.layout?.area ?? catalogue?.area ?? [0, 0, ...grid]
  return {
    grid,
    area,
    target: frame?.target_area ?? catalogue?.target_area ?? catalogue?.area ?? area,
    fixed: frame?.fixed ?? catalogue?.fixed ?? [],
    slots: frame?.slots ?? catalogue?.slots ?? [],
  }
}

export function progressOf(frame) {
  if (!frame) return null
  const workspace =
    frame.domain === "workspace" ||
    frame.workspace_routed === true ||
    frame.terms?.workspace_width !== undefined
  const routed =
    !workspace && (frame.outcome?.routed ?? frame.evidence?.routed ?? frame.clean ?? false)
  return {
    phase: frame.phase ?? PHASES[frame.kind] ?? frame.kind,
    domain: workspace ? "workspace" : "target",
    display: frame.display ?? "current",
    placed: frame.placed ?? frame.blocks?.length ?? null,
    total: frame.total ?? null,
    elapsed: frame.elapsed ?? null,
    routed,
    workspaceRouted: workspace && (frame.workspace_routed ?? frame.evidence?.routing === "pass"),
    terms: frame.terms ?? {},
    best: frame.best ?? null,
    worker: frame.worker,
    work: frame.work ?? {},
    workerWork: frame.worker_work,
    rates: frame.evidence?.rates ?? "not_checked",
  }
}

export function useFinalArtifact({ showFinal, playing, live, index, count, running }) {
  return showFinal && !running && !playing && (count === 0 || (live && index === count - 1))
}

export function progressSeries(frames, metric) {
  return ["current", "best"].map((which) => ({
    key: which,
    values: frames.map((frame, index) => {
      if (frame.display === "worker") return null
      const value = which === "best" ? frame.best?.terms?.[metric] : frame.terms?.[metric]
      return Number.isFinite(value) ? { x: frame.elapsed ?? index, y: value } : null
    }),
  }))
}

export function chartGeometry(series, width, height, cursor = null) {
  const pad = 4
  const points = series
    .flatMap((s) => s.values.map((v, i) => (typeof v === "number" ? { x: i, y: v } : v)))
    .filter((v) => v && Number.isFinite(v.x) && Number.isFinite(v.y))
  if (!points.length) return { lines: [], min: 0, max: 0, cursorX: null }
  const min = Math.min(...points.map((p) => p.y)),
    max = Math.max(...points.map((p) => p.y))
  const xmin = Math.min(...points.map((p) => p.x)),
    xmax = Math.max(...points.map((p) => p.x))
  const x = (v) => pad + ((v - xmin) / (xmax - xmin || 1)) * (width - 2 * pad)
  const y = (v) => height - pad - ((v - min) / (max - min || 1)) * (height - 2 * pad)
  const lines = series.map((s) => {
    let pen = false
    const path = s.values
      .map((value, index) => {
        const p = typeof value === "number" ? { x: index, y: value } : value
        if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) {
          pen = false
          return ""
        }
        const command = `${pen ? "L" : "M"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`
        pen = true
        return command
      })
      .join(" ")
    return { ...s, path }
  })
  return { lines, min, max, cursorX: Number.isFinite(cursor) && cursor >= 0 ? x(cursor) : null }
}
