---
title: First plan
summary: Write a scenario for a small Valley IV battery line, run the planner, and read every table it prints.
tags:
  - tutorials
  - plan
---

# First plan

This walk plans a small line in Valley IV: LC Valley Batteries from Amethyst Ore and Originium Ore. It uses only solids, so no pipes, sinks or gas are involved; the second tutorial adds those.

You need the tool installed and the dataset fetched ([Getting started](../guides/getting-started.md)).

## 1. Write the scenario

Create `battery.toml`:

```toml
mode = "balanced"
gas = false

[supply]
item_quartz_sand = "unlimited"
item_originium_ore = "unlimited"

[targets]
item_proc_battery_1 = 6

[basement]
region = "valley4"
basement_id = "infra_station"
level = 2
depot_level = 1

[recipe_overrides]
item_quartz_glass = "furnance_quartz_glass_1"
```

Read it as: raw Amethyst Ore (`item_quartz_sand`) and Originium Ore arrive without limit from the depot; you want six LC Valley Batteries per minute; you build in the Infra-Station outpost of Valley IV at basement level 2 with depot level 1; area and machine count matter equally. The override pins Amethyst Fiber to one of its two Refining Unit recipes so the planner does not have to pick.

Item and recipe ids are the game's internal ids. Find them with the dataset browser:

```bash
kohakuefda data show items | grep -i battery
kohakuefda data show recipes | grep quartz_glass
```

## 2. Plan it

```bash
kohakuefda plan battery.toml -o plan.json
```

The command prints five tables and writes `plan.json`.

**Targets.** One row per target with the requested and the achieved rate. Both read 6 here. The title carries the plan status (`ok`) and the scale (`1`): when a target cannot be met, the status becomes `degraded`, the scale drops below 1 and the achieved column shows what is possible.

**Machines.** One row per recipe the planner uses: the recipe, the machine that runs it, its mode, crafts per minute, and the machine count as `whole (exact)`. The exact count is what the flow needs; the whole count is what you build. A Packaging Unit making six batteries a minute runs at exactly one machine; the Refining Unit feeding it needs one; the Shredding Units need two because one belt of Originium Ore (30 per minute) is not enough powder.

**Item balances.** Every item that moves, per minute: produced, consumed, supplied from the depot, delivered to the target, sunk elsewhere, and the net. Every net is zero in a healthy plan. A positive net on an intermediate would mean a belt backs up and eventually stops its producer; the planner reports that as an error rather than letting it through.

**Nets and lanes.** Every producer-to-consumer flow of one item with its rate and the number of belts (or pipes) it needs. A belt carries 30 per minute and a pipe 120, so 60 per minute of powder is two belts.

**Findings.** Rule results with a severity. For this scenario there are none. Common ones are `plan.degraded` when a target is cut, `plan.power` when the machines draw more than the core supplies, and `flow.accumulates` when an item has no sink. Every id is listed in [Rules](../reference/rules.md).

## 3. Read the plan file

`plan.json` holds the same information for the next stages: the scenario, the recipe uses, the balances, the nets, the cells (identical machines grouped by recipe) and the findings. Rates are exact fractions stored as strings such as `"45/2"`; nothing in the pipeline rounds a rate.

## 4. Change something

Ask for twelve batteries a minute and plan again. The Packaging Unit becomes two machines (one makes six a minute at full speed), the Shredding Units become four, and the ore net becomes four belts. Then cap the ore:

```toml
[supply]
item_quartz_sand = "unlimited"
item_originium_ore = 60
```

The status becomes `degraded`, the scale shows the common factor every target was cut by, and `plan.degraded` names the target. Targets are absolute numbers; when the supply cannot support them the planner keeps the ratios between targets and scales all of them down together before it minimises cost. [Solver](../concepts/planning/solver.md) explains the three phases behind that.

Next: [First layout](first-layout.md).
