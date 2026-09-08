"""CP-SAT occupant of the exact slot: non-overlapping boxes in a region, the bounding box minimised."""

from kohakulayout.solvers.structural.exact.protocol import (
    Boxes,
    Infeasible,
    Placed,
    register,
)

try:
    from ortools.sat.python import (
        cp_model,
    )  # optional dependency: the occupant registers only when ortools is installed
except ImportError:  # pragma: no cover
    cp_model = None


class CpSat:
    id = "cpsat"

    def solve(
        self, boxes: Boxes, region: tuple[int, int], seconds: float = 10.0
    ) -> Placed:
        width, height = region
        model = cp_model.CpModel()
        xs, ys, ix, iy = {}, {}, [], []
        for item, (w, h) in boxes.items():
            if w > width or h > height:
                raise Infeasible(f"{item} ({w}x{h}) does not fit the region")
            xs[item] = model.NewIntVar(0, width - w, f"x_{item}")
            ys[item] = model.NewIntVar(0, height - h, f"y_{item}")
            ix.append(
                model.NewIntervalVar(xs[item], w + 1, xs[item] + w + 1, f"ix_{item}")
            )
            iy.append(
                model.NewIntervalVar(ys[item], h + 1, ys[item] + h + 1, f"iy_{item}")
            )
        model.AddNoOverlap2D(ix, iy)
        right = model.NewIntVar(0, width, "right")
        bottom = model.NewIntVar(0, height, "bottom")
        for item, (w, h) in boxes.items():
            model.Add(right >= xs[item] + w)
            model.Add(bottom >= ys[item] + h)
        model.Minimize(right + bottom)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = seconds
        status = solver.Solve(model)
        if status == cp_model.INFEASIBLE:
            raise Infeasible("no non-overlapping arrangement fits the region")
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise Infeasible(f"cp-sat stopped with status {solver.StatusName(status)}")
        return {
            item: (solver.Value(xs[item]), solver.Value(ys[item])) for item in boxes
        }


if cp_model is not None:
    register(CpSat)

__all__ = ["CpSat"]
