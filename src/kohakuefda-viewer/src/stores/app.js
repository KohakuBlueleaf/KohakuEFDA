import { defineStore } from "pinia"
import { deleteJson, getJson, openEvents, postJson } from "@/api"
import { useToastStore } from "@/stores/toasts"

const LANG_KEY = "kohakuefda.lang"
export const STAGES = ["plan", "netlist", "layout", "verify"]
const PRODUCES = {
  plan: ["plan"],
  netlist: ["netlist"],
  layout: ["placement", "layout"],
  verify: ["report", "evaluation"],
}
const FRAME_STAGES = ["layout"]
const LOG_LIMIT = 200
const REQUIREMENTS_DELAY_MS = 250

function readStoredLang() {
  try {
    return localStorage.getItem(LANG_KEY) || "en"
  } catch {
    return "en"
  }
}

export function defaultScenario() {
  return {
    supply: {},
    targets: {},
    basement: { region: "wuling", basement_id: "sky_king_flats", level: 2, depot_level: 1 },
    mode: "machines",
    mixed_lanes: true,
    gas: true,
    liquids: true,
    events: false,
    banned_machines: [],
    area_fill: null,
    natural_default: "plenty",
    gas_default: "none",
    activation: "built",
    depot: "bus",
    recipe_overrides: {},
  }
}

function emptyFrames() {
  return { layout: [] }
}

function emptyIcons() {
  return { items: {}, machines: {}, logistics: {}, missing: [] }
}

export const useAppStore = defineStore("app", {
  state: () => ({
    lang: readStoredLang(),
    dataset: null,
    meta: null,
    examples: [],
    params: {},
    icons: emptyIcons(),
    apiAvailable: false,
    artifacts: {},
    files: [],
    source: "",
    status: "idle",
    error: "",
    scenario: defaultScenario(),
    requirements: { natural: [], gathered: [], intermediates: [] },
    requirementsTimer: null,
    dropped: [],
    outcomes: [],
    alternatives: { alternatives: [], bannable: [] },
    runs: [],
    run: null,
    frames: emptyFrames(),
    log: [],
    stream: null,
    flowError: "",
    selectedStage: "plan",
    pinnedStage: false,
    drafts: {},
  }),
  getters: {
    artifactCount: (state) => state.files.length,
    plan: (state) => state.artifacts["plan.json"] ?? null,
    netlist: (state) => state.artifacts["netlist.json"] ?? null,
    placement: (state) => state.artifacts["placement.json"] ?? null,
    layout: (state) => state.artifacts["layout.json"] ?? null,
    report: (state) => state.artifacts["report.json"] ?? null,
    evaluation: (state) => state.artifacts["evaluation.json"] ?? null,
    runBusy: (state) => Boolean(state.run?.busy),
    stageStatus: (state) => (stage) => state.run?.stages?.[stage]?.status ?? "idle",
    activeStage: (state) =>
      STAGES.find((s) => ["running", "queued"].includes(state.run?.stages?.[s]?.status)) ?? "",
    iconUrl: (state) => (kind, id) =>
      state.icons?.[kind]?.[id] ? `icons/${state.icons[kind][id]}` : "",
    factoryItems(state) {
      const used = new Set()
      for (const recipe of Object.values(state.dataset?.recipes ?? {})) {
        for (const stack of [...recipe.inputs, ...recipe.outputs]) {
          used.add(stack.item_id)
        }
      }
      return [...used]
    },
    square(state) {
      const basement = state.meta?.basements?.find(
        (b) => b.id === state.scenario.basement.basement_id,
      )
      return basement?.square_by_level?.[String(state.scenario.basement.level)] ?? null
    },
  },
  actions: {
    setLang(code) {
      this.lang = code
      try {
        localStorage.setItem(LANG_KEY, code)
      } catch {
        return
      }
    },
    setResults(files, source) {
      this.artifacts = files
      this.files = Object.keys(files)
      this.source = source
      this.status = "ready"
    },
    async load() {
      if (this.status === "loading") {
        return
      }
      this.status = "loading"
      this.error = ""
      try {
        const index = await getJson("artifacts/index.json")
        const loaded = {}
        for (const name of index.files) {
          if (name.endsWith(".json")) {
            loaded[name] = await getJson(`artifacts/${name}`)
          }
        }
        this.dataset = await getJson("dataset.json")
        this.setResults(loaded, "directory")
      } catch (error) {
        this.status = "error"
        this.error = String(error)
      }
      try {
        this.meta = await getJson("api/meta")
        this.examples = await getJson("api/examples")
        this.params = await getJson("api/params")
        this.icons = await getJson("api/icons")
        this.apiAvailable = true
        await this.listRuns()
        this.refreshRequirements()
      } catch {
        this.apiAvailable = false
      }
    },
    async listRuns() {
      this.runs = await getJson("api/runs")
    },
    async fetchRequirements() {
      if (!this.apiAvailable) {
        return
      }
      try {
        this.requirements = await postJson("api/requirements", this.scenario)
        for (const item of this.requirements.natural) {
          if (!(item in this.scenario.supply) && !this.dropped.includes(item)) {
            this.scenario.supply[item] = null
          }
        }
      } catch (error) {
        this.flowError = String(error)
      }
    },
    refreshRequirements() {
      clearTimeout(this.requirementsTimer)
      this.requirementsTimer = setTimeout(() => this.fetchRequirements(), REQUIREMENTS_DELAY_MS)
    },
    closeStream() {
      if (this.stream) {
        this.stream.close()
        this.stream = null
      }
    },
    async newRun(through = "netlist") {
      const toasts = useToastStore()
      this.flowError = ""
      clearTimeout(this.requirementsTimer)
      await this.fetchRequirements()
      try {
        const summary = await postJson("api/runs", this.scenario)
        await this.openRun(summary.id)
        await this.listRuns()
        this.pinnedStage = false
        if (through) {
          await this.startStage("plan", {}, through)
        }
        return summary.id
      } catch (error) {
        this.flowError = String(error)
        toasts.error("Run", String(error))
        return null
      }
    },
    async openRun(runId) {
      this.closeStream()
      this.flowError = ""
      try {
        const summary = await getJson(`api/runs/${runId}`)
        this.run = summary
        this.log = []
        this.frames = emptyFrames()
        this.drafts = {}
        this.outcomes = []
        this.alternatives = { alternatives: [], bannable: [] }
        this.scenario = JSON.parse(JSON.stringify(summary.scenario))
        const files = {}
        for (const name of summary.artifacts) {
          files[`${name}.json`] = await getJson(`api/runs/${runId}/artifacts/${name}`)
        }
        this.setResults(files, `run ${runId}`)
        for (const stage of FRAME_STAGES) {
          if (summary.frames[stage] > 0) {
            this.frames[stage] = await getJson(`api/runs/${runId}/frames/${stage}`)
          }
        }
        if (summary.artifacts.includes("plan")) {
          this.outcomes = await getJson(`api/runs/${runId}/outcomes`)
          this.fetchAlternatives(runId)
        }
        this.selectedStage = this.bestStage()
        this.stream = openEvents(
          runId,
          summary.events,
          (event) => this.onEvent(runId, event),
          () => {},
        )
      } catch (error) {
        this.flowError = String(error)
      }
    },
    bestStage() {
      const done = STAGES.filter((s) => this.stageStatus(s) === "done")
      return done.length ? done[done.length - 1] : "plan"
    },
    async onEvent(runId, event) {
      if (!this.run || this.run.id !== runId) {
        return
      }
      if (event.kind === "frame") {
        const list = this.frames[event.stage]
        if (list && event.index !== undefined) {
          list[event.index] = event.data
        }
        return
      }
      if (event.kind !== "stage") {
        return
      }
      const toasts = useToastStore()
      const previous = this.run.stages[event.stage]?.status
      this.run.stages[event.stage] = event.data
      this.run.busy = STAGES.some((s) => ["queued", "running"].includes(this.run.stages[s]?.status))
      this.log.push({ time: event.time, stage: event.stage, ...event.data })
      if (this.log.length > LOG_LIMIT) {
        this.log.splice(0, this.log.length - LOG_LIMIT)
      }
      if (event.data.status === "idle" && previous !== "idle") {
        for (const name of PRODUCES[event.stage]) {
          delete this.artifacts[`${name}.json`]
        }
        if (FRAME_STAGES.includes(event.stage)) {
          this.frames[event.stage] = []
        }
        if (event.stage === "plan") {
          this.outcomes = []
          this.alternatives = { alternatives: [], bannable: [] }
        }
        this.files = Object.keys(this.artifacts)
      }
      if (event.data.status === "running") {
        if (FRAME_STAGES.includes(event.stage)) {
          this.frames[event.stage] = []
        }
        if (!this.pinnedStage) {
          this.selectedStage = event.stage
        }
      }
      if (event.data.status === "failed") {
        toasts.error(event.stage, event.data.error)
      }
      if (event.data.status === "cancelled") {
        toasts.warn(event.stage, "cancelled")
      }
      if (event.data.status === "done") {
        for (const name of PRODUCES[event.stage]) {
          try {
            this.artifacts[`${name}.json`] = await getJson(`api/runs/${runId}/artifacts/${name}`)
          } catch {
            delete this.artifacts[`${name}.json`]
          }
        }
        this.files = Object.keys(this.artifacts)
        if (event.stage === "plan") {
          try {
            this.outcomes = await getJson(`api/runs/${runId}/outcomes`)
          } catch {
            this.outcomes = []
          }
          this.fetchAlternatives(runId)
        }
        if (!this.run.busy) {
          if (!this.pinnedStage) {
            this.selectedStage = event.stage === "netlist" ? "plan" : event.stage
          }
          toasts.ok(event.stage, "done")
        }
      }
    },
    async startStage(stage, params, through = null) {
      if (!this.run) {
        return false
      }
      this.flowError = ""
      try {
        const data = await postJson(`api/runs/${this.run.id}/stages/${stage}`, {
          params,
          through,
        })
        this.run = { ...data.run, busy: true }
        return true
      } catch (error) {
        this.flowError = String(error)
        useToastStore().error(stage, String(error))
        return false
      }
    },
    async cancelRun() {
      if (!this.run) {
        return
      }
      try {
        await postJson(`api/runs/${this.run.id}/cancel`, {})
      } catch (error) {
        this.flowError = String(error)
      }
    },
    async deleteRun(runId) {
      try {
        await deleteJson(`api/runs/${runId}`)
        if (this.run?.id === runId) {
          this.closeStream()
          this.run = null
          this.frames = emptyFrames()
          this.outcomes = []
          this.setResults({}, "")
        }
        await this.listRuns()
      } catch (error) {
        useToastStore().error("Delete", String(error))
      }
    },
    selectStage(stage) {
      this.selectedStage = stage
      this.pinnedStage = true
    },
    draftParams(stage) {
      // The editable settings of a stage: kept as typed until reset; seeded once from the
      // run's last parameters, else the defaults. Events never overwrite a draft.
      if (!this.drafts[stage]) {
        const defaults = this.params[stage] ?? {}
        const last = this.run?.stages?.[stage]?.params ?? {}
        const draft = {}
        for (const key of Object.keys(defaults)) {
          draft[key] = key in last ? last[key] : defaults[key]
        }
        this.drafts[stage] = draft
      }
      return this.drafts[stage]
    },
    resetDraft(stage) {
      this.drafts[stage] = { ...(this.params[stage] ?? {}) }
      return this.drafts[stage]
    },
    applyExample(name) {
      const example = this.examples.find((e) => e.name === name)
      if (example) {
        this.scenario = JSON.parse(JSON.stringify(example.scenario))
        this.refreshRequirements()
      }
    },
    resetScenario() {
      this.scenario = defaultScenario()
      this.dropped = []
      this.refreshRequirements()
    },
    dropSupply(item) {
      delete this.scenario.supply[item]
      if (!this.dropped.includes(item)) {
        this.dropped.push(item)
      }
    },
    async importToml(text) {
      this.flowError = ""
      try {
        const data = await postJson("api/scenario/parse", { toml: text })
        this.scenario = data.scenario
        this.refreshRequirements()
        useToastStore().info("Scenario", "imported")
        return true
      } catch (error) {
        this.flowError = String(error)
        useToastStore().error("Import", String(error))
        return false
      }
    },
    async exportToml() {
      const data = await postJson("api/scenario/toml", this.scenario)
      return data.toml
    },
    async fetchAlternatives(runId) {
      try {
        const found = await getJson(`api/runs/${runId}/alternatives`)
        if (this.run?.id === runId) {
          this.alternatives = found
        }
      } catch {
        this.alternatives = { alternatives: [], bannable: [] }
      }
    },
    async useAlternative(alternative) {
      this.scenario = JSON.parse(JSON.stringify(alternative.scenario))
      this.refreshRequirements()
      return this.newRun("netlist")
    },
    async banAndRebuild(machineId) {
      const banned = this.scenario.banned_machines ?? []
      if (!banned.includes(machineId)) {
        this.scenario = { ...this.scenario, banned_machines: [...banned, machineId] }
      }
      this.refreshRequirements()
      return this.newRun("netlist")
    },
    async extend(outcome, option, intent, replace) {
      const targets = { ...this.scenario.targets }
      if (replace && outcome.kind === "delivered") {
        delete targets[outcome.item_id]
      }
      targets[option.product_id] = intent === "rate" ? option.rate : intent
      this.scenario = { ...this.scenario, targets }
      this.refreshRequirements()
      return this.newRun("netlist")
    },
  },
})
