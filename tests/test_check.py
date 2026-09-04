"""Update-checker classification on synthetic table sets."""

import json
from pathlib import Path

from kohakuefda.data.check import classify
from kohakuefda.data.normalize.tables import RawTables
from kohakuefda.data.sources import FACTORY_TABLES

BASE = {
    "FactoryBuildingTable": {
        "furnance_1": {"type": "6", "name": {"cn": "精炼炉", "en": "Refining Unit"}}
    },
    "FactoryMachineCraftTable": {
        "craft_a": {"machineId": "furnance_1", "progressRound": "2"}
    },
    "FactoryMachineCraftGroupTable": {"g": {"msPerRound": "1000"}},
    "FactoryMachineCrafterTable": {"furnance_1": {"modeMap": [{"modeName": "normal"}]}},
    "FactoryItemTable": {"item_a": {"phaseType": "1"}},
    "FactoryConst": {"singleConveyorLengthLimit": "110"},
    "FacBlueprintConst": {"BluePrintXLenMax": "50"},
}


def write_tables(root: Path, tables: dict) -> RawTables:
    table_dir = root / "TableCfg"
    table_dir.mkdir(parents=True)
    for name in FACTORY_TABLES:
        content = tables.get(name, {})
        (table_dir / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")
    return RawTables(table_dir)


def clone(extra: dict) -> dict:
    tables = json.loads(json.dumps(BASE))
    for name, records in extra.items():
        tables.setdefault(name, {}).update(records)
    return tables


def test_identical_sets_report_nothing(tmp_path: Path) -> None:
    old = write_tables(tmp_path / "old", BASE)
    new = write_tables(tmp_path / "new", BASE)
    assert classify(old, new) == ([], [])


def test_new_recipe_is_blind_safe(tmp_path: Path) -> None:
    old = write_tables(tmp_path / "old", BASE)
    new = write_tables(
        tmp_path / "new",
        clone(
            {
                "FactoryMachineCraftTable": {
                    "craft_b": {"machineId": "furnance_1", "progressRound": "10"}
                }
            }
        ),
    )
    safe, handler = classify(old, new)
    assert handler == []
    assert safe == ["FactoryMachineCraftTable: +1 -0 ~0"]


def test_new_building_type_and_const_need_a_handler(tmp_path: Path) -> None:
    old = write_tables(tmp_path / "old", BASE)
    new = write_tables(
        tmp_path / "new",
        clone(
            {
                "FactoryBuildingTable": {
                    "teleporter_1": {"type": "99", "name": {"cn": "", "en": "X"}}
                },
                "FactoryConst": {"teleportRange": "5"},
            }
        ),
    )
    _, handler = classify(old, new)
    assert any("new building types ['99']" in line for line in handler)
    assert any("new FactoryConst keys ['teleportRange']" in line for line in handler)


def test_new_field_is_flagged(tmp_path: Path) -> None:
    old = write_tables(tmp_path / "old", BASE)
    changed = clone({})
    changed["FactoryItemTable"]["item_a"]["weight"] = "3"
    new = write_tables(tmp_path / "new", changed)
    _, handler = classify(old, new)
    assert any("FactoryItemTable: fields added ['weight']" in line for line in handler)
