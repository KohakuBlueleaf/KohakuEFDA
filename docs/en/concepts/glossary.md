---
title: Glossary
summary: Every project-specific term: what it is, where it sits, which page covers it; and the game's own names for machines, logistics units and basements in three languages.
tags:
  - concepts
  - glossary
  - reference
---

# Glossary

Terms the docs use with a specific meaning. Each entry says what the thing is, where it lives in the pipeline, and which page explains it. Nothing here is normative: where an entry and a concept or reference page disagree, the page is right and this entry is the bug.

The second half lists the game's names for every machine, logistics unit and basement the tool knows, in English, Traditional Chinese and Simplified Chinese, straight from the dataset (`kohakuefda glossary all` prints the same). Code, artifacts and the CLI use the English names and the game's internal ids.

## Terms

### Activation

A continuous flow a Transmuting Unit needs before it runs: 6 per minute of Liquid Xiranite or Xiragen, wasting up to 30. Planned as an input, routed as a lane, checked by the evaluator. → [The factory model](foundations/the-factory-model.md#gas-and-activation).

### AIC

The Automated Industry Complex (集成工业系统), the game's factory system. Everything here is about it.

### Basement

This project's word for the game's **Core AIC Area**: the square of one outpost or hub in which machines are placed. Named in the scenario by region, id, level and depot level. → [Scenarios](../guides/scenarios.md#basement).

### Block

A cell at an anchor and rotation with a chosen port per pin, moved as a whole by the engine: every machine, the core, each Depot Bus part, each brick, each zone unit and each outside input; blocks the game binds share a group. → [Blocks and placement](layout/blocks-and-placement.md).

### Bridge

A one-cell unit letting two belts or two pipes cross, each straight through. Placed by the router at every same-kind crossing. → [Routing](layout/routing.md).

### Conduit

An underground pipe between a Conduit Inlet and a Conduit Outlet (地下暗管), up to 300 cells apart. Recorded as a link in a layout; imported from blueprints; not yet placed by the router. → [The factory model](foundations/the-factory-model.md#belts-and-pipes).

### Converger

A unit merging up to three inputs into one output; the only legal way to merge lanes. → [Routing](layout/routing.md#from-nets-to-wires).

### Core AIC Area

See Basement.

### Depot

The base's storage (仓库). Unbounded in the model; reached through Depot Loaders and Unloaders on the Depot Bus (仓库存取线). → [The factory model](foundations/the-factory-model.md#the-depot).

### Depot line

The Wuling cell holding a Depot Bus Port, its Sections and the bricks that touch them, placed and rotated as one piece. → [Machines](cells/machines.md#cells-that-touch-the-outside).

### Direct link

Two ports of different entities facing each other across an edge, connected without a belt or pipe cell between them. An assumption about the game. → [Steady state](verification/steady-state.md#the-model), [Assumptions](../dev/assumptions.md).

### Dump

A sink that destroys a fluid: the Water Treatment Unit at 30 per minute. → [Solver](planning/solver.md#constraints).

### Environment, gas zone

The 13×13 area around a Gas Dispersing Unit in which environment recipes run (环境). → [The factory model](foundations/the-factory-model.md#gas-and-activation), [Blocks and placement](layout/blocks-and-placement.md#blocks).

### Evaluation

The steady state of a layout: the flow on every segment and the utilisation of every machine. Written to `evaluation.json`. → [Steady state](verification/steady-state.md).

### Finding

One rule result: id, severity (`info`, `warning`, `error`), subject and message. Plans, netlists, layouts and reports all carry them. → [Rules](../reference/rules.md).

### Lane

One belt or pipe carrying one item, sized to the item's rate: a belt takes 30 per minute, a pipe 120. Supply lanes are packed so that one lane feeds each machine whole. → [Lanes and stability](planning/lanes-and-stability.md), [Machines](cells/machines.md).

### Layer

Ground or sky. Belts and belt units on the ground; pipes in the sky; machines and pipe units on both. → [The factory model](foundations/the-factory-model.md#the-grid-and-its-layers).

### Mode

The plan's cost tie-break: `area`, `machines` or `balanced`. → [Solver](planning/solver.md#three-phases).

### Module

A tile of the layout no larger than a game blueprint (蓝图), listed in build order. → [Modules](layout/modules.md).

### Net

In the plan: one item's flow from one producer to one consumer with its lanes. In the netlist: one item's flow between all its source pins and sink pins. → [Lanes and stability](planning/lanes-and-stability.md#nets), [Netlist](cells/netlist.md).

### Netlist

Rows with pins, and nets between pins; the input of placement and routing. → [Netlist](cells/netlist.md).

### Pin

One lane of one item on a cell's port: direction, kind, item, rate, the default port's cell and edge, and every alternative port the lane may use. → [Machines](cells/machines.md).

### Plan

The planner's output: recipe uses, machine counts, item balances, nets, cells and findings. → [Planning](planning/README.md).

### Port

A machine's connection point: a cell, an edge, belt or pipe, in or out. → [The factory model](foundations/the-factory-model.md#machines-and-ports).

### Region

Valley IV (四号谷地) or Wuling (武陵). Selects the recipes and the depot geometry. → [Why KohakuEFDA](foundations/why-kohakuefda.md#two-regions).

### Report

Every finding of a layout check, with a verdict. → [Verification](verification/README.md).

### Group

Cells the game binds by touching or containment, named on each cell: `bus` for the Depot Bus parts and the bricks that must touch them, `zone<n>` for a Gas Dispersing Unit and the machines its 13×13 must contain. A group has no shape; the engine keeps its blocks together and counts the rules they break as faults. → [Blocks and placement](layout/blocks-and-placement.md).

### Scenario

The one hand-written input: supply, targets, basement, mode, flags and overrides. → [Scenarios](../guides/scenarios.md), [Scenario file](../reference/scenario-file.md).

### Segment

An ordered list of cells carrying one belt or one pipe from an output port to an input port. → [Checking layouts](../guides/checking-layouts.md#the-layout-file).

### Slot

A brick position along a Valley IV fixed bus: the border cell a Depot Loader or Unloader stands on and the side the bus lies on. → [Machines](cells/machines.md).

### Splitter

A unit sharing one input over up to three outputs, round-robin over the outputs that are not backed up. → [The factory model](foundations/the-factory-model.md#splitters-convergers-bridges-control-ports).

### Site

Every machine at an absolute cell, on one routing grid, with the router that holds their wires. A machine enters it only through a placement that routes at the same time and undoes itself when a lane has no path, so a position that cannot be wired never exists. → [Blocks and placement](layout/blocks-and-placement.md).

### Utilisation

The fraction of full speed a machine runs at in the steady state. A recipe's machines must sum to at least the plan's exact machine count. → [Steady state](verification/steady-state.md#the-rate-rule).

## Machines

| English | 繁體中文 | 简体中文 | id |
|---|---|---|---|
| Acid Resistant Pump Mk II | 二型耐酸水泵 | 二型耐酸水泵 | `pump_2` |
| Automation-Core | 協議核心 | 协议核心 | `sp_hub_1` |
| Conduit Inlet | 暗管入口 | 暗管入口 | `udpipe_loader_1` |
| Conduit Inlet Manifold | 多口暗管入口 | 多口暗管入口 | `udpipe_loader_2` |
| Conduit Outlet | 暗管出口 | 暗管出口 | `udpipe_unloader_1` |
| Conduit Outlet Manifold | 多口暗管出口 | 多口暗管出口 | `udpipe_unloader_2` |
| Depot Bus Port | 倉庫存取線源樁 | 仓库存取线源桩 | `log_hongs_bus_source` |
| Depot Bus Section | 倉庫存取線基段 | 仓库存取线基段 | `log_hongs_bus` |
| Depot Loader | 倉庫存貨口 | 仓库存货口 | `loader_1` |
| Depot Unloader | 倉庫取貨口 | 仓库取货口 | `unloader_1` |
| Electric Pylon | 供電樁 | 供电桩 | `power_diffuser_1` |
| Expanded Crucible | 擴容反應池 | 扩容反应池 | `mix_pool_2` |
| Filling Unit | 灌裝機 | 灌装机 | `filling_powder_mc_1` |
| Fitting Unit | 配件機 | 配件机 | `component_mc_1` |
| Fluid Pump | 水泵 | 水泵 | `pump_1` |
| Fluid Tank | 儲液罐 | 储液罐 | `liquid_storager_1` |
| Fluid-Gas Transmuting Unit | 液氣轉化機 | 液气转化机 | `transmuter_1` |
| Forge of the Sky | 天有洪爐 | 天有洪炉 | `xiranite_oven_1` |
| Gas Dispersing Unit | 氣體散布機 | 气体散布机 | `vaporizer_1` |
| Gas Extractor | 氣體收集泵 | 气体收集泵 | `gas_pump_1` |
| Gas Reactor Globe | 氣體反應爐 | 气体反应炉 | `gas_reactor_1` |
| Gas Tank | 儲氣罐 | 储气罐 | `gas_storager_1` |
| Gearing Unit | 裝備原件機 | 装备原件机 | `winder_1` |
| Grinding Unit | 研磨機 | 研磨机 | `thickener_1` |
| Moulding Unit | 塑形機 | 塑形机 | `shaper_1` |
| Packaging Unit | 封裝機 | 封装机 | `tools_assebling_mc_1` |
| Planting Unit | 種植機 | 种植机 | `planter_1` |
| Protocol Stash | 協議儲存箱 | 协议储存箱 | `storager_1` |
| Purification Unit | 提純機 | 提纯机 | `liquid_purifier_1` |
| Reactor Crucible | 反應池 | 反应池 | `mix_pool_1` |
| Refining Unit | 精煉爐 | 精炼炉 | `furnance_1` |
| Seed-Picking Unit | 採種機 | 采种机 | `seedcollector_1` |
| Separating Unit | 拆解機 | 拆解机 | `dismantler_1` |
| Sewage Inlet | | 污水接入口 | `liquid_clean_gate_1` |
| Shredding Unit | 粉碎機 | 粉碎机 | `grinder_1` |
| Solid-Gas Transmuting Unit | 固氣轉化機 | 固气转化机 | `transmuter_2` |
| Sub-PAC | 次級核心 | 次级核心 | `sp_sub_hub_1` |
| Water Treatment Unit | 廢水處理機 | 废水处理机 | `liquid_cleaner_1` |
| Xiranite Pylon | 息壤供電樁 | 息壤供电桩 | `power_diffuser_2` |

## Logistics units

| English | 繁體中文 | 简体中文 | id |
|---|---|---|---|
| Transport Belt | 傳送帶 | 传送带 | `grid_belt_01` |
| Pipe | 管道 | 管道 | `log_pipe_01` |
| Splitter | 分流器 | 分流器 | `log_splitter` |
| Converger | 匯流器 | 汇流器 | `log_converger` |
| Pipe Splitter | 管道分流器 | 管道分流器 | `log_pipe_splitter` |
| Pipe Converger | 管道匯流器 | 管道汇流器 | `log_pipe_converger` |
| Belt Bridge | 物流橋 | 物流桥 | `log_connector` |
| Pipe Bridge | 管道橋 | 管道桥 | `log_pipe_connector` |
| Item Control Port | 物品准入口 | 物品准入口 | `log_conditioner` |
| Pipe Control Port | 管道准入口 | 管道准入口 | `log_pipe_conditioner` |

## Basements

| English | 简体中文 | Region | Square by level | Depot |
|---|---|---|---|---|
| The Hub | 枢纽区 | Valley IV | unknown | fixed bus |
| Refugee Camp | 难民暂居处 | Valley IV | unknown | fixed bus |
| Infra-Station | 基建前站 | Valley IV | 24×27, 32×32, 40×40 | fixed bus |
| Reconstruction HQ | 重建指挥部 | Valley IV | 24×27, 32×32, 40×40 | fixed bus |
| Wuling City | 武陵城 | Wuling | unknown | laid bus |
| Sky King Flats | | Wuling | 30×30, 40×40, 50×50 | laid bus |
| Cardiac Remediation Station | | Wuling | 30×30, 40×40, 50×50 | laid bus |
| Xiranflow Cloudseeder Station | | Wuling | 30×30, 40×40, 50×50 | laid bus |

Basement ids are the snake-case English names (`infra_station`, `sky_king_flats`). Blank cells are names the dataset does not hold yet.
