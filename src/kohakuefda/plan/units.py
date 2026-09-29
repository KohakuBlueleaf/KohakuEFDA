"""Repeat units from the plan: recursive integral grouping from the sinks upstream.

A recipe use whose solid output flows only into one other use at an integral machine ratio
joins that use's tile, so many per copy; a use that is shared, or whose ratio is not integral,
or part of whose output leaves for the depot, heads a tile of its own with as many copies as
it has machines; the uses of a cycle (seeds and planters) form one node whose copies are the
greatest common divisor of their machine counts. Liquids bind nothing: conduits carry them to
an outlet beside each consumer wherever it stands. Every use with attached feeders is a tile;
the ones attached to nothing are the top level, and the item flows between different
top-level tiles are the global nets.
"""

import logging
from collections import Counter
from fractions import Fraction
from math import gcd

from kohakuefda.model.cells import CellInstance
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.items import Phase
from kohakuefda.model.plan import Plan, RecipeUse
from kohakuefda.model.units import Flow, Hierarchy, Tile

log = logging.getLogger(__name__)
WORLD = ""


def _components(nodes: list[str], edges: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components in a reverse topological order (sinks first), Tarjan's."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    out: list[list[str]] = []
    counter = 0

    def visit(node: str) -> None:
        nonlocal counter
        index[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for other in sorted(edges.get(node, ())):
            if other not in index:
                visit(other)
                low[node] = min(low[node], low[other])
            elif other in on_stack:
                low[node] = min(low[node], index[other])
        if low[node] == index[node]:
            component: list[str] = []
            while True:
                top = stack.pop()
                on_stack.discard(top)
                component.append(top)
                if top == node:
                    break
            out.append(sorted(component))

    for node in sorted(nodes):
        if node not in index:
            visit(node)
    return out


def uses_of(dataset: Dataset, plan: Plan) -> list[RecipeUse]:
    return [
        u
        for u in plan.recipes
        if u.machines > 0 and dataset.recipes.get(u.recipe_id) is not None
    ]


def shares(
    dataset: Dataset, plan: Plan, uses: list[RecipeUse]
) -> dict[tuple[str, str, str], Fraction]:
    """Of each output item of a use, the share taken by each consuming use, by (producer, item, consumer)."""
    demand: dict[str, dict[str, Fraction]] = {}
    for use in uses:
        recipe = dataset.recipes[use.recipe_id]
        for stack in recipe.inputs:
            demand.setdefault(stack.item_id, {})[use.recipe_id] = (
                use.machines_exact * recipe.input_rate(stack.item_id)
            )
    out: dict[tuple[str, str, str], Fraction] = {}
    for use in uses:
        recipe = dataset.recipes[use.recipe_id]
        for stack in recipe.outputs:
            if dataset.items[stack.item_id].phase is not Phase.SOLID:
                continue
            balance = plan.items.get(stack.item_id)
            total = balance.produced + balance.supplied if balance else Fraction(0)
            for consumer, taken in demand.get(stack.item_id, {}).items():
                if consumer != use.recipe_id and total > 0:
                    out[use.recipe_id, stack.item_id, consumer] = taken / total
    return out


def extract(dataset: Dataset, plan: Plan) -> Hierarchy:
    """The plan's repeat units and the flows between the top-level ones."""
    uses = uses_of(dataset, plan)
    by_id = {u.recipe_id: u for u in uses}
    share = shares(dataset, plan, uses)
    edges: dict[str, set[str]] = {}
    for producer, _, consumer in share:
        edges.setdefault(producer, set()).add(consumer)
    components = split_open_cycles(dataset, _components(list(by_id), edges), share)
    while True:
        node_of = {r: "+".join(c) for c in components for r in c}
        copies = {"+".join(c): gcd(*(by_id[r].machines for r in c)) for c in components}
        consumers: dict[str, set[str]] = {}
        taken: dict[tuple[str, str], Fraction] = {}
        for (producer, item, consumer), part in share.items():
            node, other = node_of[producer], node_of[consumer]
            if node != other:
                consumers.setdefault(node, set()).add(other)
            taken[producer, item] = taken.get((producer, item), Fraction(0)) + part
        merged = merge_uneven(dataset, plan, components, copies, consumers, taken)
        if merged is None:
            break
        components = merged
    parent: dict[str, str | None] = {}
    per: dict[str, int] = {}
    for component in components:
        node = "+".join(component)
        targets = consumers.get(node, set())
        whole = all(part == 1 for (r, _), part in taken.items() if r in component)
        parent[node] = None
        if len(targets) == 1 and whole:
            target = next(iter(targets))
            if copies[node] % copies[target] == 0:
                parent[node] = target
                per[node] = copies[node] // copies[target]
    cut_mixed_ports(dataset, plan, uses, components, node_of, parent, per)
    tiles: list[Tile] = []
    for component in components:
        node = "+".join(component)
        tiles.append(
            Tile(
                id=node,
                recipes=list(component),
                per_copy={r: by_id[r].machines // copies[node] for r in component},
                copies=copies[node],
                members={m: per[m] for m, p in parent.items() if p == node},
                parent=parent[node],
            )
        )
    hierarchy = Hierarchy(tiles=tiles)
    rims_of(dataset, plan, hierarchy)
    roots = {t.id: hierarchy.root(t.id) for t in tiles}
    flows: list[Flow] = []
    for producer, item, consumer in sorted(share):
        source, sink = roots[node_of[producer]], roots[node_of[consumer]]
        if source != sink and not any(
            f.item_id == item and f.source == source and f.sink == sink for f in flows
        ):
            flows.append(Flow(item_id=item, source=source, sink=sink))
    for balance in plan.items.values():
        makers = sorted(
            {
                roots[node_of[u.recipe_id]]
                for u in uses
                if any(
                    s.item_id == balance.item_id
                    for s in dataset.recipes[u.recipe_id].outputs
                )
            }
        )
        users = sorted(
            {
                roots[node_of[u.recipe_id]]
                for u in uses
                if any(
                    s.item_id == balance.item_id
                    for s in dataset.recipes[u.recipe_id].inputs
                )
            }
        )
        if balance.supplied > 0:
            flows += [
                Flow(item_id=balance.item_id, source=WORLD, sink=t) for t in users
            ]
        if balance.delivered + balance.sunk > 0:
            flows += [
                Flow(item_id=balance.item_id, source=t, sink=WORLD) for t in makers
            ]
    hierarchy.flows = flows
    log.info(
        "hierarchy: %d tile(s), %d at the top, %d flow(s) between them",
        len(tiles),
        len(hierarchy.top),
        sum(1 for f in flows if f.source != WORLD and f.sink != WORLD),
    )
    return hierarchy


def split_open_cycles(
    dataset: Dataset,
    components: list[list[str]],
    share: dict[tuple[str, str, str], Fraction],
) -> list[list[str]]:
    """A cycle whose member sends one item both to the cycle and out of it is taken apart into
    its uses: that item leaves the member's output face for two places, so the cycle could
    never stand as one unit with its rim; the loop then runs at the top level."""
    out: list[list[str]] = []
    for component in components:
        inside = set(component)
        open_cycle = len(component) > 1 and any(
            producer in inside
            and consumer not in inside
            and any(
                (p2, i2, c2) in share
                for (p2, i2, c2) in share
                if p2 == producer and i2 == item and c2 in inside
            )
            for (producer, item, consumer) in share
        )
        if open_cycle:
            out += [[r] for r in component]
        else:
            out.append(component)
    return out


def merge_uneven(
    dataset: Dataset,
    plan: Plan,
    components: list[list[str]],
    copies: dict[str, int],
    consumers: dict[str, set[str]],
    taken: dict[tuple[str, str], Fraction],
) -> list[list[str]] | None:
    """The components with one merged into its only consumer when everything it makes goes
    there but its copies do not divide the consumer's, so a flow that cannot be cut into equal
    units stays inside one; never when the consumer also takes a solid from elsewhere, since
    a member fed from inside and outside could not stand on the unit's rim. None when nothing
    merges."""
    supplied = {i for i, b in plan.items.items() if b.supplied > 0}
    for component in components:
        node = "+".join(component)
        targets = consumers.get(node, set())
        whole = all(part == 1 for (r, _), part in taken.items() if r in component)
        if len(targets) != 1 or not whole:
            continue
        target = next(iter(targets))
        if copies[node] % copies[target] == 0:
            continue
        other = next(c for c in components if "+".join(c) == target)
        made = {
            s.item_id for r in [*component, *other] for s in dataset.recipes[r].outputs
        }
        if any(
            (s.item_id in supplied or s.item_id not in made)
            and dataset.items[s.item_id].phase is Phase.SOLID
            for r in other
            for s in dataset.recipes[r].inputs
        ):
            continue
        rest = [c for c in components if c is not component and c is not other]
        return [*rest, sorted(component + other)]
    return None


def cut_mixed_ports(
    dataset: Dataset,
    plan: Plan,
    uses: list[RecipeUse],
    components: list[list[str]],
    node_of: dict[str, str],
    parent: dict[str, str | None],
    per: dict[str, int],
) -> None:
    """Detach the feeders of every use that also takes an input from outside its tile or
    sends one output both into its tile and out of it, and detach every use that feeds its
    tile but also sends an output outside it: a machine's inputs share one face and its
    outputs the other, so one joined to the world on a face cannot be joined to its tile on
    that face too; repeated until no tile changes."""
    nodes = {"+".join(c): c for c in components}
    supplied = {i for i, b in plan.items.items() if b.supplied > 0}
    outside = {
        i for i, b in plan.items.items() if b.delivered > 0 or b.sink_kind is not None
    }

    def subtree(node: str) -> set[str]:
        out = {node}
        for child, p in parent.items():
            if p == node:
                out |= subtree(child)
        return out

    def top_of(node: str) -> str:
        above = parent.get(node)
        return node if above is None else top_of(above)

    def solid(item_id: str) -> bool:
        return dataset.items[item_id].phase is Phase.SOLID

    def consumers_of(item_id: str) -> set[str]:
        return {
            node_of[u.recipe_id]
            for u in uses
            if any(t.item_id == item_id for t in dataset.recipes[u.recipe_id].inputs)
        }

    changed = True
    while changed:
        changed = False
        for node, component in nodes.items():
            children = [c for c, p in parent.items() if p == node]
            if children:
                inside = subtree(node)
                makers_inside = {
                    s.item_id
                    for other in inside
                    for r in nodes[other]
                    for s in dataset.recipes[r].outputs
                }
                external = any(
                    s.item_id in supplied or s.item_id not in makers_inside
                    for r in component
                    for s in dataset.recipes[r].inputs
                    if solid(s.item_id)
                )
                shared_output = any(
                    consumers_of(s.item_id) & inside
                    and not consumers_of(s.item_id) <= inside
                    for r in component
                    for s in dataset.recipes[r].outputs
                    if solid(s.item_id)
                )
                if external or shared_output:
                    for child in children:
                        parent[child] = None
                        per.pop(child, None)
                    changed = True
            if parent.get(node) is None:
                continue
            tile = subtree(top_of(node))
            leaving = any(
                not solid(s.item_id)
                or s.item_id in outside
                or not consumers_of(s.item_id) <= tile
                for r in component
                for s in dataset.recipes[r].outputs
            )
            if leaving:
                parent[node] = None
                per.pop(node, None)
                changed = True


def rims_of(dataset: Dataset, plan: Plan, hierarchy: Hierarchy) -> None:
    """Name on each top-level tile the recipes that take a solid input from outside it."""
    supplied = {i for i, b in plan.items.items() if b.supplied > 0}
    for top in hierarchy.top:
        inside = {
            r
            for t in hierarchy.tiles
            if hierarchy.root(t.id) == top.id
            for r in t.recipes
        }
        makers = {s.item_id for r in inside for s in dataset.recipes[r].outputs}
        top.rim = sorted(
            r
            for r in inside
            if any(
                (s.item_id in supplied or s.item_id not in makers)
                and dataset.items[s.item_id].phase is Phase.SOLID
                for s in dataset.recipes[r].inputs
            )
        )


def unit_name(tile_id: str, copy: int) -> str:
    return f"{tile_id}#{copy}"


def assign_units(hierarchy: Hierarchy, cells: list[CellInstance]) -> None:
    """Name each recipe cell's top-level tile and copy, the cells of a recipe taken in order
    and cut into as many equal runs as the tile has copies; an outlet takes the unit of the
    consumer its net key names unless that consumer stands on the tile's rim; inlets, and a
    side cell some copies lack, are built once and keep None, so every copy of a tile holds
    the same cells and every rim cell faces the outside alone."""
    recipes: dict[str, str] = {}
    copies: dict[str, int] = {}
    for tile in hierarchy.tiles:
        top = hierarchy.root(tile.id)
        for recipe_id in tile.recipes:
            recipes[recipe_id] = top
            copies[recipe_id] = hierarchy.tile(top).copies
    counts: dict[str, int] = {}
    for cell in cells:
        if cell.recipe_id in recipes:
            counts[cell.recipe_id] = counts.get(cell.recipe_id, 0) + 1
    seen: dict[str, int] = {}
    by_id: dict[str, CellInstance] = {c.id: c for c in cells}
    for cell in cells:
        if cell.recipe_id in recipes:
            top = recipes[cell.recipe_id]
            run = max(1, counts[cell.recipe_id] // copies[cell.recipe_id])
            cell.unit = unit_name(top, seen.get(cell.recipe_id, 0) // run)
            seen[cell.recipe_id] = seen.get(cell.recipe_id, 0) + 1
    rims = {r for tile in hierarchy.top for r in tile.rim}
    for cell in cells:
        if cell.kind == "outlet" and cell.pins and cell.pins[0].net:
            mate = by_id.get(cell.pins[0].net.rsplit("_", 1)[0])
            inside = mate is not None and mate.recipe_id not in rims
            cell.unit = mate.unit if inside else None
    demote_groups(cells)
    demote_extras(cells)


def demote_groups(cells: list[CellInstance]) -> None:
    """A group (a zone, the bus) whose members are not all in one unit copy is built once."""
    members: dict[str, list[CellInstance]] = {}
    for cell in cells:
        if cell.group:
            members.setdefault(cell.group, []).append(cell)
    for group in members.values():
        if len({c.unit for c in group}) > 1:
            for cell in group:
                cell.unit = None


Shape = tuple[str, str, str, tuple[str, ...]]


def shape_of(cell: CellInstance) -> Shape:
    """The kind, recipe and rated pin signature required for interchangeable instances."""
    return (
        cell.kind,
        cell.machine_id,
        cell.recipe_id or "",
        tuple(sorted(f"{p.direction}:{p.item_id}:{p.rate}" for p in cell.pins)),
    )


def demote_extras(cells: list[CellInstance]) -> None:
    """Cells beyond the shape multiset every copy of their tile shares are built once."""
    per_copy: dict[str, dict[str, Counter[Shape]]] = {}
    for cell in cells:
        if cell.unit is not None:
            tile, copy = cell.unit.rsplit("#", 1)
            per_copy.setdefault(tile, {}).setdefault(copy, Counter())[
                shape_of(cell)
            ] += 1
    common: dict[str, Counter[Shape]] = {}
    for tile, runs in per_copy.items():
        shared = None
        for shapes in runs.values():
            shared = shapes if shared is None else shared & shapes
        common[tile] = shared or Counter()
    taken: dict[str, Counter[Shape]] = {}
    for cell in cells:
        if cell.unit is None:
            continue
        tile = cell.unit.rsplit("#", 1)[0]
        used = taken.setdefault(cell.unit, Counter())
        shape = shape_of(cell)
        if used[shape] < common[tile][shape]:
            used[shape] += 1
        else:
            cell.unit = None


__all__ = [
    "WORLD",
    "Shape",
    "assign_units",
    "cut_mixed_ports",
    "demote_extras",
    "demote_groups",
    "extract",
    "merge_uneven",
    "rims_of",
    "shape_of",
    "shares",
    "split_open_cycles",
    "unit_name",
    "uses_of",
]
