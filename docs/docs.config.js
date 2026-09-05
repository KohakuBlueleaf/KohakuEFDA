/**
 * KohakuEFDA docs site configuration.
 *
 * Multi-locale: every locale has its own sidebar labels and landing copy; the
 * Markdown files live under `docs/<locale>/`. Pages missing in a non-default
 * locale fall back to English (`missingTranslation: "fallback"`), so every
 * sidebar lists the full page set.
 */

const sidebarStructure = {
  overview: ["README.md"],
  tutorials: ["tutorials/README.md", "tutorials/first-plan.md", "tutorials/first-layout.md"],
  guides: [
    "guides/README.md",
    "guides/getting-started.md",
    "guides/scenarios.md",
    "guides/checking-layouts.md",
    "guides/importing-blueprints.md",
    "guides/viewer.md",
    "guides/dataset-updates.md",
  ],
  conceptsRoot: ["concepts/README.md"],
  conceptsFoundations: [
    "concepts/foundations/README.md",
    "concepts/foundations/why-kohakuefda.md",
    "concepts/foundations/the-factory-model.md",
    "concepts/foundations/the-pipeline.md",
  ],
  conceptsPlanning: [
    "concepts/planning/README.md",
    "concepts/planning/recipe-graph.md",
    "concepts/planning/solver.md",
    "concepts/planning/lanes-and-stability.md",
  ],
  conceptsCells: [
    "concepts/cells/README.md",
    "concepts/cells/machines.md",
    "concepts/cells/netlist.md",
  ],
  conceptsLayout: [
    "concepts/layout/README.md",
    "concepts/layout/blocks-and-placement.md",
    "concepts/layout/routing.md",
    "concepts/layout/modules.md",
  ],
  conceptsVerification: [
    "concepts/verification/README.md",
    "concepts/verification/geometry-rules.md",
    "concepts/verification/steady-state.md",
  ],
  conceptsTail: ["concepts/glossary.md"],
  reference: [
    "reference/README.md",
    "reference/cli.md",
    "reference/scenario-file.md",
    "reference/artifacts.md",
    "reference/rules.md",
    "reference/dataset.md",
  ],
  framework: [
    "framework/README.md",
    "framework/manual.md",
    "framework/reference.md",
    "framework/backends.md",
  ],
  dev: [
    "dev/README.md",
    "dev/internals.md",
    "dev/dependency-graph.md",
    "dev/testing.md",
    "dev/frontend.md",
    "dev/native.md",
    "dev/assumptions.md",
  ],
}

function sidebar(labels) {
  return [
    { text: labels.overview, items: sidebarStructure.overview },
    { text: labels.tutorials, items: sidebarStructure.tutorials },
    { text: labels.guides, items: sidebarStructure.guides },
    {
      text: labels.concepts,
      items: [
        ...sidebarStructure.conceptsRoot,
        { text: labels.foundations, items: sidebarStructure.conceptsFoundations },
        { text: labels.planning, items: sidebarStructure.conceptsPlanning },
        { text: labels.cells, items: sidebarStructure.conceptsCells },
        { text: labels.layout, items: sidebarStructure.conceptsLayout },
        { text: labels.verification, items: sidebarStructure.conceptsVerification },
        ...sidebarStructure.conceptsTail,
      ],
    },
    { text: labels.reference, items: sidebarStructure.reference },
    { text: labels.framework, items: sidebarStructure.framework },
    { text: labels.dev, items: sidebarStructure.dev },
  ]
}

const enLabels = {
  overview: "Overview",
  tutorials: "Tutorials",
  guides: "Guides",
  concepts: "Concepts",
  foundations: "Foundations",
  planning: "Planning",
  cells: "Cells and netlists",
  layout: "Placement and routing",
  verification: "Verification",
  reference: "Reference",
  framework: "Solver framework",
  dev: "Development",
}

const zhTWLabels = {
  overview: "總覽",
  tutorials: "教學",
  guides: "使用指南",
  concepts: "核心概念",
  foundations: "基礎",
  planning: "規劃",
  cells: "單元與網表",
  layout: "擺放與佈線",
  verification: "驗證",
  reference: "參考",
  framework: "求解器框架",
  dev: "開發",
}

const zhCNLabels = {
  overview: "总览",
  tutorials: "教程",
  guides: "使用指南",
  concepts: "核心概念",
  foundations: "基础",
  planning: "规划",
  cells: "单元与网表",
  layout: "摆放与布线",
  verification: "验证",
  reference: "参考",
  framework: "求解器框架",
  dev: "开发",
}

const enHomeCards = [
  {
    title: "First plan",
    description: "Write a scenario, run the planner, read machine counts, lanes and stability.",
    to: "/docs/tutorials/first-plan",
  },
  {
    title: "First layout",
    description: "Place and route the plan inside a basement, verify it, open it in the viewer.",
    to: "/docs/tutorials/first-layout",
  },
  {
    title: "The factory model",
    description: "Belts, pipes, layers, ports, splitters, sinks, the depot and basements as the tool sees them.",
    to: "/docs/concepts/foundations/the-factory-model",
  },
  {
    title: "The pipeline",
    description: "Scenario to plan to netlist to layout to report: what each stage decides and writes.",
    to: "/docs/concepts/foundations/the-pipeline",
  },
  {
    title: "CLI reference",
    description: "Every command and flag: data, plan, netlist, layout, check, render, view.",
    to: "/docs/reference/cli",
  },
  {
    title: "Rules",
    description: "Every finding the planner, netlist, layout and verifier can raise, with its severity.",
    to: "/docs/reference/rules",
  },
]

const zhTWHomeCards = [
  {
    title: "第一個規劃",
    description: "撰寫情境、執行規劃器，讀懂設施數、線道與穩定性。",
    to: "/docs/tutorials/first-plan",
  },
  {
    title: "第一個佈局",
    description: "在核心區域內擺放與佈線、驗證，並在檢視器中開啟。",
    to: "/docs/tutorials/first-layout",
  },
  {
    title: "工廠模型",
    description: "傳送帶、管道、層、埠、分流器、匯、倉庫與核心區域在工具眼中的樣子。",
    to: "/docs/concepts/foundations/the-factory-model",
  },
  {
    title: "流程",
    description: "情境 → 規劃 → 網表 → 佈局 → 報告：每一階段決定什麼、輸出什麼。",
    to: "/docs/concepts/foundations/the-pipeline",
  },
  {
    title: "命令列參考",
    description: "每個命令與旗標：data、plan、netlist、layout、check、render、view。",
    to: "/docs/reference/cli",
  },
  {
    title: "規則",
    description: "規劃器、網表、佈局與驗證器會提出的每一項結果及其等級。",
    to: "/docs/reference/rules",
  },
]

const zhCNHomeCards = [
  {
    title: "第一个规划",
    description: "编写场景、运行规划器，读懂设施数、线道与稳定性。",
    to: "/docs/tutorials/first-plan",
  },
  {
    title: "第一个布局",
    description: "在核心区域内摆放与布线、验证，并在查看器中打开。",
    to: "/docs/tutorials/first-layout",
  },
  {
    title: "工厂模型",
    description: "传送带、管道、层、端口、分流器、汇、仓库与核心区域在工具眼中的样子。",
    to: "/docs/concepts/foundations/the-factory-model",
  },
  {
    title: "流程",
    description: "场景 → 规划 → 网表 → 布局 → 报告：每一阶段决定什么、输出什么。",
    to: "/docs/concepts/foundations/the-pipeline",
  },
  {
    title: "命令行参考",
    description: "每个命令与参数：data、plan、netlist、layout、check、render、view。",
    to: "/docs/reference/cli",
  },
  {
    title: "规则",
    description: "规划器、网表、布局与验证器会提出的每一项结果及其等级。",
    to: "/docs/reference/rules",
  },
]

export default {
  docsDir: "./docs",
  projectRoot: ".",
  defaultLocale: "en",
  missingTranslation: "fallback",
  markdown: {
    stripTitleHeading: true,
  },
  locales: {
    en: {
      label: "English",
      docsSubdir: "en",
      homePage: "README.md",
      ui: "en",
      site: {
        title: "KohakuEFDA",
        description:
          "End Field Design Automation: an offline planner and layout generator for the Automated Industry Complex in Arknights: Endfield.",
      },
      home: {
        kicker: "Design automation for the AIC",
        title: "KohakuEFDA Docs",
        description:
          "Give it supply rates, targets and a basement; it plans recipes and machine counts, sizes lanes, places every machine with the core and the pylons, routes belts and pipes, checks the game's rules and renders the result. The docs cover the factory model, the pipeline stage by stage, every command and artifact, and the development notes.",
        actions: [
          { text: "Getting started", to: "/docs/guides/getting-started" },
          { text: "GitHub", href: "https://github.com/KohakuBlueleaf/KohakuEFDA", variant: "secondary" },
        ],
        cards: enHomeCards,
      },
      sidebar: sidebar(enLabels),
    },
    "zh-TW": {
      label: "繁體中文",
      docsSubdir: "zh-TW",
      homePage: "README.md",
      ui: "zh-TW",
      site: {
        title: "KohakuEFDA",
        description: "終末地設計自動化：《明日方舟：終末地》集成工業系統的離線規劃與佈局產生器。",
      },
      home: {
        kicker: "集成工業系統的設計自動化",
        title: "KohakuEFDA 文件",
        description:
          "給它供應速率、目標與核心區域；它規劃配方與設施數、決定線道、擺放設施列、佈線傳送帶與管道、檢查遊戲規則並輸出結果。文件涵蓋工廠模型、逐階段的流程、每個命令與產物，以及開發說明。",
        actions: [
          { text: "快速開始", to: "/docs/guides/getting-started" },
          { text: "GitHub", href: "https://github.com/KohakuBlueleaf/KohakuEFDA", variant: "secondary" },
        ],
        cards: zhTWHomeCards,
      },
      sidebar: sidebar(zhTWLabels),
    },
    "zh-CN": {
      label: "简体中文",
      docsSubdir: "zh-CN",
      homePage: "README.md",
      ui: "zh-CN",
      site: {
        title: "KohakuEFDA",
        description: "终末地设计自动化：《明日方舟：终末地》集成工业系统的离线规划与布局生成器。",
      },
      home: {
        kicker: "集成工业系统的设计自动化",
        title: "KohakuEFDA 文档",
        description:
          "给它供应速率、目标与核心区域；它规划配方与设施数、决定线道、摆放设施行、布线传送带与管道、检查游戏规则并输出结果。文档涵盖工厂模型、逐阶段的流程、每个命令与产物，以及开发说明。",
        actions: [
          { text: "快速开始", to: "/docs/guides/getting-started" },
          { text: "GitHub", href: "https://github.com/KohakuBlueleaf/KohakuEFDA", variant: "secondary" },
        ],
        cards: zhCNHomeCards,
      },
      sidebar: sidebar(zhCNLabels),
    },
  },
}
