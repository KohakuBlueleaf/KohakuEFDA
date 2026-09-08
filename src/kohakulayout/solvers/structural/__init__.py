"""The structural family: a floorplan over macros and leaves, mutated, scored by a surrogate, legalised through the builder."""

from fractions import Fraction
from itertools import count
from typing import Any

from kohakulayout.errors import NotAvailable
from kohakulayout.solvers.base import BaseSolver
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.registry import register
from kohakulayout.solvers.structural import exact as exact_slot
from kohakulayout.solvers.structural.floorplan import Rows, item_size, items_of
from kohakulayout.solvers.structural.legalize import legalize
from kohakulayout.solvers.structural.representation import (
    REPRESENTATIONS,
    Coordinate,
    Representation,
)
from kohakulayout.solvers.structural.representation import get as get_representation
from kohakulayout.solvers.structural.surrogate import surrogate


@register
class Floorplan(BaseSolver):
    id = "floorplan"
    resume = "continues"
    params = (
        Param(
            name="representation",
            type="choice",
            default="rows",
            choices=("rows", "coordinate"),
        ),
        Param(
            name="channel",
            type="int",
            default=2,
            doc="cells of channel above and between rows; two leave room for a wire and a crossing",
        ),
        Param(name="gap", type="int", default=2, doc="cells between items in a row"),
        Param(
            name="rows",
            type="int",
            default=0,
            doc="rows in the initial floorplan; 0 picks a square",
        ),
        Param(
            name="exact",
            type="choice",
            default="none",
            choices=("none", "cpsat", "milp"),
            doc="an exact packing for the initial floorplan",
        ),
        Param(name="exact_seconds", type="float", default=5.0),
        Param(
            name="steps",
            type="int",
            default=200,
            doc="mutations proposed; 0 stops after construction",
        ),
        Param(name="until_budget", type="bool", default=True),
        Param(name="wire_weight", type="fraction", default=Fraction(1, 4)),
        Param(
            name="construct_tries",
            type="int",
            default=32,
            doc="mutations tried when the initial floorplan does not legalise",
        ),
    )

    def representation(self) -> Any:
        name = self.opts["representation"]
        if name == "rows":
            return Rows(
                channel=self.opts["channel"],
                gap=self.opts["gap"],
                rows=self.opts["rows"],
            )
        return get_representation(name)

    def score(self, structure: Any, ctx: Any) -> Fraction:
        return surrogate(self.rep, structure, ctx, Fraction(self.opts["wire_weight"]))

    def construct(self, ctx: Any) -> None:
        self.rep = self.representation()
        self.structure = self.rep.initial(ctx, ctx.rng)
        if self.opts["exact"] != "none":
            self.structure = self.packed(ctx, self.structure)
        assessment = legalize(self.rep, self.structure, ctx)
        tries = 0
        while assessment is None and tries < self.opts["construct_tries"]:
            candidate = self.rep.mutate(self.structure, ctx.rng)
            assessment = legalize(self.rep, candidate, ctx)
            if assessment is not None:
                self.structure = candidate
            tries += 1
            ctx.frame("floorplan")
        self.best_score = self.score(self.structure, ctx)

    def packed(self, ctx: Any, structure: Any) -> Any:
        """The rows re-ordered by an exact packing of the items' boxes, when an occupant is installed."""
        occupant = exact_slot.get(self.opts["exact"])
        world = ctx.world
        boxes = {item: item_size(world, item, 0) for item in items_of(world)}
        try:
            placed = occupant.solve(
                boxes,
                (world.fabric.width, world.fabric.height),
                self.opts["exact_seconds"],
            )
        except exact_slot.Infeasible as exc:
            raise NotAvailable(
                f"the exact packing found no arrangement: {exc}"
            ) from exc
        by_row: dict[int, list[str]] = {}
        for item, (x, y) in placed.items():
            by_row.setdefault(y, []).append((x, item))
        rows = [[item for _, item in sorted(by_row[y])] for y in sorted(by_row)]
        return {"rows": rows, "rot": dict.fromkeys(boxes, 0)}

    def improve(self, ctx: Any) -> None:
        if ctx.best_assessment is None:
            return
        steps = self.opts["steps"]
        budget = ctx.budget
        loop = (
            count()
            if steps
            and self.opts["until_budget"]
            and (budget.units is not None or budget.seconds is not None)
            else range(steps)
        )
        for _ in loop:
            candidate = self.rep.mutate(self.structure, ctx.rng)
            estimate = self.score(candidate, ctx)
            ctx.budget.charge(1)
            if estimate > self.best_score:
                continue
            before = ctx.best_assessment
            assessment = legalize(self.rep, candidate, ctx)
            if assessment is not None and ctx.best_assessment is not before:
                self.structure, self.best_score = candidate, estimate
            elif assessment is not None:
                ctx.restore_best()
            ctx.frame("floorplan")


__all__ = [
    "REPRESENTATIONS",
    "Coordinate",
    "Floorplan",
    "Representation",
    "Rows",
    "legalize",
    "surrogate",
]
