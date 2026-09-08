"""The state checker: the world's obligations as assertions, mounted in tests and behind a flag at runtime."""

from typing import Any

from kohakulayout.errors import StateError
from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.ir.refusal import STAGES
from kohakulayout.physics.protocol import Anchor
from kohakulayout.state.kernel import holder_kind
from kohakulayout.state.snapshot import Token


class StateCheck:
    """Watches a world and raises :class:`StateError` on the first broken obligation."""

    def __init__(self, strict: bool = True) -> None:
        self.strict = strict
        self.events: list[str] = []
        self.failures: list[str] = []

    def mount(self, world: Any) -> "StateCheck":
        world.checker = self
        return self

    def _fail(self, message: str) -> None:
        self.failures.append(message)
        if self.strict:
            raise StateError(message)

    def _stage(self, subject: str, result: Any, stages: tuple[str, ...]) -> None:
        if result is None:
            return
        if not result.stage:
            self._fail(f"{subject}: refusal without a stage")
        elif result.stage not in stages and result.stage not in STAGES:
            self._fail(f"{subject}: refusal stage {result.stage!r} is not in the chain")

    def on_place(
        self, world: Any, cell_id: str, anchor: Anchor, result: Any, pre_digest: str
    ) -> None:
        self.events.append(
            f"place {cell_id} {anchor.x},{anchor.y} r{anchor.rot} -> {result.stage if result else 'ok'}"
        )
        self._stage(f"place {cell_id}", result, world.physics.stages)
        if result is not None and world.digest() != pre_digest:
            self._fail(
                f"place {cell_id}: refused at {result.stage} but the digest moved"
            )
        self.holders(world)

    def on_route(self, world: Any, net_id: str, result: Any, pre_digest: str) -> None:
        self.events.append(f"route {net_id} -> {result.stage if result else 'ok'}")
        self._stage(f"route {net_id}", result, world.physics.stages)
        if result is not None and world.digest() != pre_digest:
            self._fail(
                f"route {net_id}: refused at {result.stage} but the digest moved"
            )
        self.holders(world)

    def on_restore(self, world: Any, token: Token, kernel: Any) -> None:
        self.events.append(f"restore seq={token.seq}")
        if world.kernel is not kernel:
            self._fail("restore replaced the kernel instead of loading into it")
        digest = world.digest()
        if digest != token.digest:
            self._fail(
                f"restore produced digest {digest[:12]} for a token of {token.digest[:12]}"
            )
        self.holders(world)

    def holders(self, world: Any) -> None:
        """Every placement, wire, unit and reservation holds exactly its cells, and nothing else holds any."""
        expected: dict[str, dict[str, set]] = {}
        for cell_id, placement in world.placements.items():
            fp = world.footprint_of(cell_id)
            cells = set(
                footprint_cells(
                    placement.x, placement.y, fp.width, fp.height, placement.rot
                )
            )
            expected[f"cell:{cell_id}"] = {
                layer: set(cells) for layer in world.layers_for(fp)
            }
        for net_id, wire in world.wires.items():
            layers: dict[str, set] = {}
            for segment in wire.segments:
                layers.setdefault(segment.layer, set()).update(segment.cells)
            expected[f"wire:{net_id}"] = layers
        for unit_id, unit in world.units.items():
            fp = world.library[unit.footprint]
            cells = set(footprint_cells(unit.x, unit.y, fp.width, fp.height, unit.rot))
            expected[f"unit:{unit_id}"] = {
                layer: set(cells) for layer in world.layers_for(fp)
            }
        for reservation in world.reservations.values():
            expected[f"reserve:{reservation.tag}"] = {
                reservation.layer: set(reservation.cells)
            }
        for holder, layers in expected.items():
            held = world.kernel.cells_of(holder)
            for layer, cells in layers.items():
                if set(held.get(layer, ())) != cells:
                    self._fail(
                        f"{holder} holds {sorted(held.get(layer, ()))} on {layer}, expected {sorted(cells)}"
                    )
        for layer in world.kernel.layers:
            for holder in world.kernel.holders_on(layer):
                if holder not in expected:
                    self._fail(
                        f"{holder} holds cells on {layer} but the world has no record of it"
                    )
        self.reservations(world)

    def reservations(self, world: Any) -> None:
        for reservation in world.reservations.values():
            for xy in reservation.cells:
                for holder in world.kernel.holders_at(reservation.layer, xy):
                    kind, ref = holder_kind(holder)
                    if kind != "wire":
                        continue
                    carrier = world.netlist.nets[ref].carrier
                    if reservation.carrier is None or carrier != reservation.carrier:
                        self._fail(
                            f"reservation {reservation.tag} is crossed by {holder} ({carrier}) at {xy}"
                        )

    def report(self) -> str:
        lines = [*self.events, *(f"FAIL {f}" for f in self.failures)]
        return "\n".join(lines)


__all__ = ["StateCheck"]
