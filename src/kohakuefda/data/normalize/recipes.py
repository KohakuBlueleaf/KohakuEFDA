"""FactoryMachineCraftTable + craft groups + crafter modes → ``Recipe`` records."""

from fractions import Fraction

from kohakuefda.data.normalize.tables import RawTables, as_int, names_of
from kohakuefda.model.items import Phase
from kohakuefda.model.names import Names
from kohakuefda.model.recipes import Binding, Recipe, Stack

ENV_NAMES = {"0": None, "1": "stable", "2": "humid", "3": "acrid", "4": "xiranite"}
EVENT_MARK = "activity"


def is_event(craft_id: str, inputs: list[Stack], outputs: list[Stack]) -> bool:
    """A limited-time recipe: its id or one of its items carries the event mark (RCP-06)."""
    return EVENT_MARK in craft_id or any(
        EVENT_MARK in s.item_id for s in inputs + outputs
    )


def _stacks(groups: list[dict]) -> list[Stack]:
    return [
        Stack(item_id=entry["id"], count=as_int(entry["count"]))
        for group in groups
        for entry in group.get("group", [])
    ]


def _bindings(raw: list[dict]) -> list[Binding]:
    out: list[Binding] = []
    for index, entry in enumerate(raw):
        phases = entry.get("pipePortPhaseType") or []
        phase = Phase(as_int(phases[0])) if phases else None
        out.append(
            Binding(
                buffer=index,
                ports=[as_int(p) for p in entry.get("bindingPortIndices", [])],
                phase=phase,
            )
        )
    return out


def _mode_of(crafters: dict, machine_id: str, group_id: str) -> str:
    for mode in crafters.get(machine_id, {}).get("modeMap", []):
        if mode.get("groupName") == group_id:
            return mode["modeName"]
    return "normal"


def build_recipes(tables: RawTables) -> dict[str, Recipe]:
    crafts = tables["FactoryMachineCraftTable"]
    groups = tables["FactoryMachineCraftGroupTable"]
    crafters = tables["FactoryMachineCrafterTable"]
    recipes: dict[str, Recipe] = {}
    for craft_id, record in crafts.items():
        group = groups.get(record["formulaGroupId"], {})
        ms_per_round = as_int(group.get("msPerRound"), 1000)
        seconds = Fraction(as_int(record["progressRound"]) * ms_per_round, 1000)
        en, cn = names_of(record, "formulaDesc")
        inputs = _stacks(record.get("ingredients", []))
        outputs = _stacks(record.get("outcomes", []))
        recipes[craft_id] = Recipe(
            id=craft_id,
            names=Names(en=en or craft_id, zh_cn=cn),
            machine_id=record["machineId"],
            mode=_mode_of(crafters, record["machineId"], record["formulaGroupId"]),
            group_id=record["formulaGroupId"],
            inputs=inputs,
            outputs=outputs,
            seconds=seconds,
            env=ENV_NAMES.get(
                str(record.get("gasEnv", "0")), str(record.get("gasEnv"))
            ),
            event=is_event(craft_id, inputs, outputs),
            buffers={k: as_int(v) for k, v in record.get("buffers", {}).items()},
            belt_in=_bindings(group.get("ingredientBufferBinding", [])),
            belt_out=_bindings(group.get("outcomeBufferBinding", [])),
            pipe_in=_bindings(group.get("pipeIngredientBufferBinding", [])),
            pipe_out=_bindings(group.get("pipeOutcomeBufferBinding", [])),
        )
    return recipes
