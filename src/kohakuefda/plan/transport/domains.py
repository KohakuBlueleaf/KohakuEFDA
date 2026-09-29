"""Recipe-compatible physical port domains and deterministic matching."""

from collections.abc import Iterable

from kohakuefda.model.cells import CellInstance
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.machines import Port, PortDir, PortType
from kohakuefda.plan.transport.model import TransportError

MAX_UNIONS = 4096


def allowed_ports(
    dataset: Dataset, cell: CellInstance, item: str, direction: str
) -> tuple[Port, ...]:
    """Retain recipe bindings and explicitly configured non-recipe port domains."""
    machine = dataset.machines.get(cell.machine_id)
    if machine is None:
        return ()
    recipe = dataset.recipes.get(cell.recipe_id)
    if recipe is not None:
        indices = set(
            dataset.input_ports(recipe, item)
            if direction == "in"
            else dataset.output_ports(recipe, item)
        )
    else:
        indices = {
            port.index
            for pin in cell.pins
            if pin.item_id == item and pin.direction == direction and pin.kind == "belt"
            for port in pin.alternatives
        }
    return tuple(
        p
        for p in machine.ports_of(PortDir(direction), PortType.BELT)
        if p.index in indices
    )


def unions(domains: Iterable[frozenset[int]]) -> list[frozenset[int]]:
    """Enumerate distinct unions required for Hall's port-capacity inequalities."""
    result = {frozenset()}
    for domain in sorted(set(domains), key=lambda d: tuple(sorted(d))):
        result.update([prior | domain for prior in result])
        if len(result) > MAX_UNIONS:
            raise TransportError("physical port-domain unions exceed the model budget")
    return sorted((d for d in result if d), key=lambda d: (len(d), tuple(sorted(d))))


def match_ports(domains: list[tuple[int, ...]]) -> list[int]:
    """Return a distinct allowed physical port for each lane, or raise on a Hall violation."""
    owner: dict[int, int] = {}

    def augment(lane: int, visited: set[int]) -> bool:
        for port in sorted(domains[lane]):
            if port in visited:
                continue
            visited.add(port)
            if port not in owner or augment(owner[port], visited):
                owner[port] = lane
                return True
        return False

    for lane in sorted(range(len(domains)), key=lambda i: (len(domains[i]), i)):
        if not augment(lane, set()):
            raise TransportError(
                "direct lanes have no injective compatible-port assignment"
            )
    selected = {lane: port for port, lane in owner.items()}
    return [selected[lane] for lane in range(len(domains))]


__all__ = ["MAX_UNIONS", "allowed_ports", "match_ports", "unions"]
