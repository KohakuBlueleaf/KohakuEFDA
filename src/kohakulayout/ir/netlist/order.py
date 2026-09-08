"""Producer-before-consumer order over a flat netlist, with the back edges of loops listed."""

from collections.abc import Iterable


def flow_order(
    cells: Iterable[str], edges: Iterable[tuple[str, str]]
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Kahn's order over ``edges`` (producer, consumer); a cycle is broken at the smallest id.

    Returns the order and the edges that point backwards in it, which are the loops.
    """
    ids = sorted(set(cells))
    succ: dict[str, set[str]] = {c: set() for c in ids}
    indeg: dict[str, int] = dict.fromkeys(ids, 0)
    seen: set[tuple[str, str]] = set()
    for producer, consumer in edges:
        if producer == consumer or (producer, consumer) in seen:
            continue
        seen.add((producer, consumer))
        succ.setdefault(producer, set()).add(consumer)
        indeg[consumer] = indeg.get(consumer, 0) + 1
        indeg.setdefault(producer, 0)
    remaining = set(indeg)
    ready = sorted(c for c in remaining if indeg[c] == 0)
    order: list[str] = []
    while remaining:
        if not ready:
            ready = [min(remaining)]
        current = ready.pop(0)
        if current not in remaining:
            continue
        remaining.discard(current)
        order.append(current)
        for nxt in sorted(succ.get(current, ())):
            if nxt in remaining:
                indeg[nxt] -= 1
                if indeg[nxt] <= 0 and nxt not in ready:
                    ready.append(nxt)
        ready.sort()
    position = {c: i for i, c in enumerate(order)}
    back = tuple(sorted((p, c) for p, c in seen if position[p] >= position[c]))
    return tuple(order), back
