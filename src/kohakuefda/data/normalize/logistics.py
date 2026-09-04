"""Belt, pipe, router, connector, valve and conduit tables → logistics units and constants."""

from fractions import Fraction

from kohakuefda.data.normalize.ports import map_port
from kohakuefda.data.normalize.tables import RawTables, as_int, names_of
from kohakuefda.model.logistics import LogisticsConstants, LogisticsUnit
from kohakuefda.model.machines import PortDir
from kohakuefda.model.names import Names

UNIT_TABLES = (
    ("FactoryGridBeltTable", "beltData", "belt", False),
    ("FactoryLiquidPipeTable", "pipeData", "pipe", True),
    ("FactoryGridRouterTable", "gridUnitData", "router", False),
    ("FactoryLiquidRouterTable", "liquidUnitData", "router", True),
    ("FactoryGridConnecterTable", "gridUnitData", "bridge", False),
    ("FactoryLiquidConnectorTable", "liquidUnitData", "bridge", True),
    ("FactoryBoxValveTable", "gridUnitData", "control", False),
    ("FactoryFluidValveTable", "liquidUnitData", "control", True),
)


def _unit_ports(
    record: dict, width: int, depth: int, is_pipe: bool, owner: str
) -> list:
    ports = []
    for direction, key in ((PortDir.IN, "inputPorts"), (PortDir.OUT, "outputPorts")):
        for index, raw in enumerate(record.get(key, [])):
            ports.append(map_port(raw, index, direction, width, depth, is_pipe, owner))
    return ports


def build_logistics(tables: RawTables) -> dict[str, LogisticsUnit]:
    units: dict[str, LogisticsUnit] = {}
    for table, data_key, kind, is_pipe in UNIT_TABLES:
        for unit_id, record in tables[table].items():
            data = record.get(data_key, {})
            rng = record.get("range", {})
            width = as_int(rng.get("x"), 1)
            depth = as_int(rng.get("z"), 1)
            en, cn = names_of(data)
            units[unit_id] = LogisticsUnit(
                id=unit_id,
                names=Names(en=en, zh_cn=cn),
                kind=f"{'pipe' if is_pipe else 'belt'}_{kind}",
                width=width,
                depth=depth,
                height=as_int(rng.get("y"), 1),
                ms_per_round=as_int(data.get("msPerRound"), 2000),
                volume=as_int(data.get("volume"), 1),
                ports=_unit_ports(record, width, depth, is_pipe, unit_id),
            )
    for unit_id, record in tables["FactoryUndergroundPipeTable"].items():
        building = tables["FactoryBuildingTable"].get(unit_id, {})
        en, cn = names_of(building)
        units[unit_id] = LogisticsUnit(
            id=unit_id,
            names=Names(en=en, zh_cn=cn),
            kind="conduit",
            width=as_int(building.get("range", {}).get("width"), 3),
            depth=as_int(building.get("range", {}).get("depth"), 3),
            height=as_int(building.get("range", {}).get("height"), 5),
            ms_per_round=as_int(record.get("msPerRound"), 500),
            capacity=as_int(record.get("capacity")),
        )
    return units


def build_constants(tables: RawTables) -> LogisticsConstants:
    const = tables["FactoryConst"]
    blueprint = tables["FacBlueprintConst"]
    belt = next(iter(tables["FactoryGridBeltTable"].values()))["beltData"]
    pipe = next(iter(tables["FactoryLiquidPipeTable"].values()))["pipeData"]
    hub = tables["FactoryHubTable"].get("sp_hub_1", {})
    limits = {
        domain_id: as_int(record.get("domainSpeedLimitCount"))
        for domain_id, record in tables["DomainDataTable"].items()
        if record.get("domainSpeedLimitCount") is not None
    }
    return LogisticsConstants(
        belt_per_min=Fraction(60000, as_int(belt["msPerRound"])),
        pipe_per_min=Fraction(
            60000 * as_int(pipe.get("volume"), 1), as_int(pipe["msPerRound"])
        ),
        belt_run_max=as_int(const["singleConveyorLengthLimit"]),
        pipe_run_max=as_int(const["singleFluidConveyorLengthLimit"]),
        conduit_link_max=as_int(const["udPipeConnectMaxLength"]),
        fluid_router_limit=as_int(const["levelFluidRouterCountLimit"]),
        farmland_limit=as_int(const["farmlandSoilCountLimit"]),
        blueprint_max_x=as_int(blueprint["BluePrintXLenMax"]),
        blueprint_max_z=as_int(blueprint["BluePrintZLenMax"]),
        blueprint_max_nodes=as_int(blueprint["BlueprintNodeCountLimit"]),
        building_height_diff_max=as_int(const["maxBuildingCoverGridHeightDiff"]),
        control_port_limit=limits,
        core_power=as_int(hub.get("powerGenerate"), 200),
        core_power_storage=as_int(hub.get("powerStorageCapacity"), 100000),
    )
