"""Import an IndustrialPlanner blueprint (schemaVersion 5) into a ``Layout``.

IndustrialPlanner stores one entity per belt or pipe cell (``belt_straight_1x1``,
``belt_turn_cw_1x1`` …) with a heading rotation (0 = +x, 90 = +y), machines by their game
``definitionId`` in their registry's default orientation (our rotation + 180 for most
machines, + 0 for the depot loader and unloader), recipes by their own slugs
(``r_<machine>_<outputs>_from_<inputs>_<mode>``) and conduit pairs as ``slotLinks``.
Recipes are scored by word overlap of the slug against item ids; a machine with several
recipe channels keeps the best-scoring recipe among those whose outputs match its port
accept rules (all candidates when no rule matches); pump slugs pick the source fluid the
same way. Positions may be negative; the result is shifted into a non-negative box.
"""

import json
from pathlib import Path

from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge
from kohakuefda.model.items import Phase
from kohakuefda.model.layout import Cell, Layout, Link, Placed, Segment, Unit
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.scenario import BasementRef

HEADING_STEP = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}
HEADING_EDGE = {0: Edge.E, 90: Edge.S, 180: Edge.W, 270: Edge.N}
DEFAULT_ROTATION_OFFSET = 180
ROTATION_OFFSETS = {"unloader_1": 0, "loader_1": 0}
UNIT_IDS = {
    "log_splitter",
    "log_converger",
    "log_connector",
    "log_conditioner",
    "log_pipe_splitter",
    "log_pipe_converger",
    "log_pipe_connector",
    "log_pipe_conditioner",
}
DEFINITION_ALIASES = {"water_pump_1": "pump_1"}
CONDUIT_INLET = "udpipe_loader"
CONDUIT_OUTLET = "udpipe_unloader"
SOURCE_PHASES = {
    "pump_1": Phase.LIQUID,
    "pump_2": Phase.LIQUID,
    "gas_pump_1": Phase.GAS,
}
STOP_WORDS = {"r", "from", "and", "basic", "chrono", "default", "item", "liquid", "gas"}
MIN_RECIPE_SCORE = 0.5
MARGIN = 1


def _words(text: str) -> set[str]:
    return {w for w in text.split("_") if w and not w.isdigit() and w not in STOP_WORDS}


def _overlap(theirs: set[str], ours: set[str]) -> float:
    union = theirs | ours
    return len(theirs & ours) / len(union) if union else 0.0


def recipe_scores(
    dataset: Dataset, machine_id: str, definition: str, slug: str
) -> dict[str, float]:
    """Per recipe of ``machine_id``: output-word overlap plus input-word overlap with the slug."""
    machine_words = _words(machine_id) | _words(definition)
    head, _, tail = slug.partition("_from_")
    out_words = _words(head) - machine_words
    in_words = _words(tail) - machine_words
    scores: dict[str, float] = {}
    for recipe in dataset.recipes_of(machine_id):
        ours_out = set().union(*(_words(s.item_id) for s in recipe.outputs))
        ours_in = set().union(*(_words(s.item_id) for s in recipe.inputs))
        scores[recipe.id] = _overlap(out_words, ours_out - machine_words) + _overlap(
            in_words, ours_in - machine_words
        )
    return scores


def match_recipe(
    dataset: Dataset, machine_id: str, definition: str, slug: str
) -> Recipe | None:
    """The best-scoring recipe for one slug, or ``None`` below the score floor."""
    scores = recipe_scores(dataset, machine_id, definition, slug)
    if not scores:
        return None
    best = max(scores, key=scores.__getitem__)
    return dataset.recipes[best] if scores[best] >= MIN_RECIPE_SCORE else None


def match_source_item(dataset: Dataset, machine_id: str, slug: str) -> str | None:
    """The fluid a pump slug names, among items of the pump's phase."""
    phase = SOURCE_PHASES[machine_id]
    words = _words(slug) - _words(machine_id)
    best: str | None = None
    best_score = 0.0
    for item in dataset.items.values():
        if item.phase is not phase:
            continue
        score = _overlap(words, _words(item.id))
        if score > best_score:
            best, best_score = item.id, score
    return best


def _accept_items(raw_config: dict) -> set[str]:
    """Item ids named by ``portGroups[i].ports[j].acceptRule`` entries."""
    out: set[str] = set()
    for key, value in raw_config.items():
        if "acceptRule" in key and isinstance(value, dict):
            item = value.get("base", {}).get("itemId")
            if item:
                out.add(item)
    return out


def _choose_recipe(
    dataset: Dataset, definition: str, original: str, raw_config: dict
) -> Recipe | None:
    """Best recipe over all channels, restricted to those whose outputs match the accept rules."""
    channels = raw_config.get("channelRecipes", {})
    slugs = list(channels.values()) if isinstance(channels, dict) else []
    best: dict[str, float] = {}
    for slug in slugs:
        for recipe_id, score in recipe_scores(
            dataset, definition, original, slug
        ).items():
            if score >= MIN_RECIPE_SCORE:
                best[recipe_id] = max(best.get(recipe_id, 0.0), score)
    accept = _accept_items(raw_config)
    matching = {
        recipe_id: score
        for recipe_id, score in best.items()
        if {s.item_id for s in dataset.recipes[recipe_id].outputs} & accept
    }
    pool = matching or best
    if not pool:
        return None
    return dataset.recipes[max(pool, key=pool.__getitem__)]


def _kind(definition: str) -> str | None:
    if definition.startswith("belt_"):
        return "belt"
    if definition.startswith("pipe_"):
        return "pipe"
    return None


def _successor(cell: Cell, heading: int, definition: str, tiles: dict) -> Cell | None:
    """Next tile cell: straight tiles follow their heading, turn tiles pick the neighbour."""
    step = HEADING_STEP.get(heading % 360)
    if step is None:
        return None
    candidate = (cell[0] + step[0], cell[1] + step[1])
    if candidate in tiles or "turn" not in definition:
        return candidate
    for dx, dy in HEADING_STEP.values():
        other = (cell[0] + dx, cell[1] + dy)
        if other in tiles:
            return other
    return None


def _chains(tiles: dict[Cell, tuple[int, str]]) -> list[list[Cell]]:
    """Follow belt/pipe tiles heading by heading into ordered cell chains."""
    nxt: dict[Cell, Cell] = {}
    for cell, (heading, definition) in tiles.items():
        successor = _successor(cell, heading, definition, tiles)
        if successor is not None:
            nxt[cell] = successor
    has_prev = set(nxt.values())
    chains: list[list[Cell]] = []
    seen: set[Cell] = set()
    for start in sorted(tiles):
        if start in has_prev or start in seen:
            continue
        chain = [start]
        seen.add(start)
        while (
            chain[-1] in nxt and nxt[chain[-1]] in tiles and nxt[chain[-1]] not in seen
        ):
            chain.append(nxt[chain[-1]])
            seen.add(chain[-1])
        chains.append(chain)
    for cell in sorted(tiles):
        if cell not in seen:
            chains.append([cell])
            seen.add(cell)
    return chains


def _machine(
    dataset: Dataset,
    entity_id: str,
    entity: dict,
    definition: str,
    x: int,
    y: int,
    rotation: int,
) -> Placed:
    raw_config = entity.get("config", {})
    config: dict[str, str] = {}
    lock = next(
        (
            v
            for k, v in raw_config.items()
            if k.endswith(".lock") and isinstance(v, str)
        ),
        None,
    )
    if lock:
        config["item"] = lock
    recipe = None
    if definition in SOURCE_PHASES:
        channels = raw_config.get("channelRecipes", {})
        slug = next(iter(channels.values()), "") if isinstance(channels, dict) else ""
        item = match_source_item(dataset, definition, slug) if slug else None
        if item:
            config["item"] = item
    else:
        recipe = _choose_recipe(dataset, definition, entity["definitionId"], raw_config)
    offset = ROTATION_OFFSETS.get(definition, DEFAULT_ROTATION_OFFSET)
    return Placed(
        id=entity_id,
        machine_id=definition,
        x=x,
        y=y,
        rotation=(rotation + offset) % 360,
        mode=recipe.mode if recipe else None,
        recipe_id=recipe.id if recipe else None,
        config=config,
    )


def import_industrial_planner(
    dataset: Dataset, path: Path, region: Region = Region.WULING
) -> Layout:
    """Read a blueprint JSON file and return our ``Layout``."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    entities = raw.get("entities", {})
    xs = [e["position"]["x"] for e in entities.values()]
    ys = [e["position"]["y"] for e in entities.values()]
    shift_x = MARGIN - min(xs, default=0)
    shift_y = MARGIN - min(ys, default=0)
    machines: list[Placed] = []
    units: list[Unit] = []
    tiles: dict[str, dict[Cell, tuple[int, str]]] = {"belt": {}, "pipe": {}}
    for key, entity in entities.items():
        entity_id = str(entity.get("id", key))
        definition = DEFINITION_ALIASES.get(
            entity["definitionId"], entity["definitionId"]
        )
        x = entity["position"]["x"] + shift_x
        y = entity["position"]["y"] + shift_y
        rotation = int(entity.get("rotation", 0)) % 360
        kind = _kind(definition)
        if kind:
            tiles[kind][(x, y)] = (rotation, definition)
        elif definition in UNIT_IDS:
            units.append(
                Unit(id=entity_id, unit_id=definition, x=x, y=y, rotation=rotation)
            )
        elif definition in dataset.machines:
            machines.append(
                _machine(dataset, entity_id, entity, definition, x, y, rotation)
            )
    segments: list[Segment] = []
    for kind in ("belt", "pipe"):
        for index, chain in enumerate(_chains(tiles[kind])):
            heading = HEADING_EDGE.get(tiles[kind][chain[0]][0] % 360)
            segments.append(
                Segment(id=f"{kind}{index}", kind=kind, cells=chain, heading=heading)
            )
    definitions = {m.id: m.machine_id for m in machines}
    links = []
    for link in raw.get("slotLinks", []):
        outlet = link.get("source", {}).get("entityId", "")
        inlet = link.get("target", {}).get("entityId", "")
        if definitions.get(outlet, "").startswith(CONDUIT_OUTLET) and definitions.get(
            inlet, ""
        ).startswith(CONDUIT_INLET):
            links.append(Link(inlet=inlet, outlet=outlet))
    max_x = max((u.x + 1 for u in units), default=0)
    max_y = max((u.y + 1 for u in units), default=0)
    for m in machines:
        width, depth = dataset.machines[m.machine_id].size(m.rotation)
        max_x = max(max_x, m.x + width)
        max_y = max(max_y, m.y + depth)
    for cells in tiles.values():
        for x, y in cells:
            max_x = max(max_x, x + 1)
            max_y = max(max_y, y + 1)
    return Layout(
        dataset_version=dataset.version.id,
        basement=BasementRef(
            region=region,
            basement_id=str(raw.get("baseId", "")),
            level=1,
            depot_level=1,
        ),
        width=max_x + MARGIN,
        height=max_y + MARGIN,
        machines=machines,
        units=units,
        segments=segments,
        links=links,
        notes=f"imported from IndustrialPlanner blueprint {raw.get('name', '')}",
    )
