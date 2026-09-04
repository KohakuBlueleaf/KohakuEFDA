"""Filled containers are named by their contents, so every item the factory uses has its own name."""

from pathlib import Path

import pytest

from kohakuefda.data.normalize.build import base_name
from kohakuefda.model.dataset import Dataset

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def test_recipe_items_have_distinct_names(dataset: Dataset) -> None:
    used = {s.item_id for r in dataset.recipes.values() for s in r.inputs + r.outputs}
    names = [dataset.items[i].names.en for i in used]
    assert len(names) == len(set(names)), sorted(n for n in names if names.count(n) > 1)
    zh = [dataset.items[i].names.get("zh-CN") for i in used]
    assert len(zh) == len(set(zh))


def test_filled_bottle_carries_its_contents(dataset: Dataset) -> None:
    water = dataset.items["item_liquid_water"].names
    bottle = dataset.items["item_fbottle_copper_water"].names
    empty = dataset.items["item_copper_bottle"].names
    assert bottle.en == f"{empty.en} ({water.en})"
    assert bottle.zh_cn == f"{empty.zh_cn}（{water.get('zh-CN')}）"
    assert base_name(bottle.en) == empty.en
    assert base_name(empty.en) == empty.en
