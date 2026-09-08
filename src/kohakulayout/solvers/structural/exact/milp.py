"""HiGHS occupant of the exact slot: the same packing as a mixed-integer program with big-M disjunctions."""

from kohakulayout.solvers.structural.exact.protocol import (
    Boxes,
    Infeasible,
    Placed,
    register,
)

try:
    import highspy  # optional dependency: the occupant registers only when highspy is installed
except ImportError:  # pragma: no cover
    highspy = None


class Milp:
    id = "milp"

    def solve(
        self, boxes: Boxes, region: tuple[int, int], seconds: float = 10.0
    ) -> Placed:
        width, height = region
        items = sorted(boxes)
        for item in items:
            w, h = boxes[item]
            if w > width or h > height:
                raise Infeasible(f"{item} ({w}x{h}) does not fit the region")
        model = highspy.Highs()
        model.setOptionValue("output_flag", False)
        model.setOptionValue("time_limit", float(seconds))
        inf = highspy.kHighsInf
        x = {i: model.addVariable(0, width - boxes[i][0]) for i in items}
        y = {i: model.addVariable(0, height - boxes[i][1]) for i in items}
        right = model.addVariable(0, width)
        bottom = model.addVariable(0, height)
        big = width + height + 2
        for i in items:
            model.addConstr(right - x[i] >= boxes[i][0])
            model.addConstr(bottom - y[i] >= boxes[i][1])
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                i, j = items[a], items[b]
                flags = [model.addVariable(0, 1) for _ in range(4)]
                for flag in flags:
                    model.changeColIntegrality(
                        flag.index, highspy.HighsVarType.kInteger
                    )
                model.addConstr(
                    x[i] + boxes[i][0] + 1 - x[j] - big * (1 - flags[0]) <= 0
                )
                model.addConstr(
                    x[j] + boxes[j][0] + 1 - x[i] - big * (1 - flags[1]) <= 0
                )
                model.addConstr(
                    y[i] + boxes[i][1] + 1 - y[j] - big * (1 - flags[2]) <= 0
                )
                model.addConstr(
                    y[j] + boxes[j][1] + 1 - y[i] - big * (1 - flags[3]) <= 0
                )
                model.addConstr(sum(flags) >= 1)
        for var in list(x.values()) + list(y.values()):
            model.changeColIntegrality(var.index, highspy.HighsVarType.kInteger)
        model.minimize(right + bottom)
        status = model.getModelStatus()
        if status == highspy.HighsModelStatus.kInfeasible:
            raise Infeasible("no non-overlapping arrangement fits the region")
        solution = model.getSolution()
        if not solution.value_valid:
            raise Infeasible(
                f"highs stopped with status {model.modelStatusToString(status)}"
            )
        values = solution.col_value
        result = {
            i: (round(values[x[i].index]), round(values[y[i].index])) for i in items
        }
        del inf
        return result


if highspy is not None:
    register(Milp)

__all__ = ["Milp"]
