"""FactoryBuildingTable + FactoryMachineCrafterTable → ``Machine`` records."""

from kohakuefda.data.normalize.ports import map_port
from kohakuefda.data.normalize.tables import RawTables, as_int, names_of
from kohakuefda.model.machines import Machine, Mode, PortDir
from kohakuefda.model.names import Names

SKIP_KINDS = {"42", "21"}


def _skip(building_id: str, record: dict) -> bool:
    if record.get("type") in SKIP_KINDS:
        return True
    en, _ = names_of(record)
    return building_id.endswith("_nop_1") or "dg002" in building_id or not en


def _modes(crafter: dict | None) -> list[Mode]:
    if not crafter:
        return []
    unlocked = crafter.get("modeUnlockDefaultMap", {})
    return [
        Mode(
            name=m["modeName"],
            group_id=m["groupName"] or None,
            unlocked_by_default=bool(unlocked.get(m["modeName"], True)),
            env_mode=bool(m.get("isEnvMode", False)),
        )
        for m in crafter.get("modeMap", [])
    ]


def build_machines(tables: RawTables) -> dict[str, Machine]:
    buildings = tables["FactoryBuildingTable"]
    crafters = tables["FactoryMachineCrafterTable"]
    machines: dict[str, Machine] = {}
    for building_id, record in buildings.items():
        if _skip(building_id, record):
            continue
        rng = record["range"]
        width, depth, height = (
            as_int(rng["width"]),
            as_int(rng["depth"]),
            as_int(rng["height"]),
        )
        ports = []
        for direction, key in (
            (PortDir.IN, "inputPorts"),
            (PortDir.OUT, "outputPorts"),
        ):
            for raw in record.get(key, []):
                ports.append(
                    map_port(
                        raw,
                        as_int(raw["index"]),
                        direction,
                        width,
                        depth,
                        bool(raw.get("isPipe")),
                        building_id,
                    )
                )
        en, cn = names_of(record)
        machines[building_id] = Machine(
            id=building_id,
            names=Names(en=en, zh_cn=cn),
            kind=str(record["type"]),
            width=width,
            depth=depth,
            height=height,
            model_height=float(record.get("modelHeight") or 0),
            ports=ports,
            power=as_int(record.get("powerConsume")),
            needs_power=bool(record.get("needPower")),
            capacity_cost=as_int(record.get("bandwidth")),
            modes=_modes(crafters.get(building_id)),
            place_domains=list(record.get("placeDomains", [])),
            recommend_domains=list(record.get("recommendDomains", [])),
        )
    return machines
