"""Every name the planner can print has English, zh-CN and zh-TW forms."""

from pathlib import Path

import pytest

from kohakuefda.model.dataset import Dataset

DATASET = (
    Path(__file__).resolve().parents[1] / "data" / "1.5.3@9764758-3" / "dataset.json"
)
FIXED_MAP_FEATURES = {"liquid_clean_gate_1", "liquid_recycle_gate_1"}


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def test_recipe_items_are_trilingual(dataset: Dataset) -> None:
    used = {s.item_id for r in dataset.recipes.values() for s in r.inputs + r.outputs}
    for item_id in sorted(used):
        names = dataset.items[item_id].names
        assert names.en and names.zh_cn and names.zh_tw, (item_id, names)


def test_producing_machines_and_logistics_are_trilingual(dataset: Dataset) -> None:
    producers = {r.machine_id for r in dataset.recipes.values()}
    for machine_id in sorted(producers | {"sp_hub_1", "sp_sub_hub_1", "storager_1"}):
        names = dataset.machines[machine_id].names
        assert names.en and names.zh_cn and names.zh_tw, (machine_id, names)
    for unit in dataset.logistics.values():
        assert unit.names.en and unit.names.zh_cn and unit.names.zh_tw, unit.id


def test_only_fixed_features_and_sim_plots_lack_traditional_chinese(
    dataset: Dataset,
) -> None:
    missing = {m.id for m in dataset.machines.values() if not m.names.zh_tw}
    assert missing <= FIXED_MAP_FEATURES | {
        m for m in missing if m.startswith("soil_") and "fast" in m
    }
