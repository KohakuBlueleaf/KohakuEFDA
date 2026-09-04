"""Every crafting recipe against the wiki's recipe modules, recorded in ``wiki_recipes.json``:
facility, stacks, time and environment, both directions."""

from pathlib import Path

import pytest

from kohakuefda.data.reference import (
    crafting_recipes,
    dataset_index,
    dataset_key,
    describe,
    is_event,
    load_wiki,
    recipe_differences,
    wiki_key,
)
from kohakuefda.model.dataset import Dataset

ROOT = Path(__file__).resolve().parents[1]
DATASET = Dataset.load(ROOT / "data" / "1.5.3@9764758-3" / "dataset.json")
WIKI = load_wiki(ROOT / "tests" / "fixtures" / "wiki_recipes.json")
INDEX = dataset_index(DATASET)
WIKI_KEYS = {wiki_key(r) for r in crafting_recipes(WIKI)}
CRAFTS = crafting_recipes(WIKI)


@pytest.mark.parametrize("recipe", CRAFTS, ids=[describe(wiki_key(r)) for r in CRAFTS])
def test_wiki_recipe_is_in_the_dataset(recipe: dict) -> None:
    mine = INDEX.get(wiki_key(recipe))
    assert mine is not None, describe(wiki_key(recipe))
    assert recipe_differences(DATASET, recipe, mine) == []


@pytest.mark.parametrize("recipe_id", sorted(DATASET.recipes))
def test_dataset_recipe_is_on_the_wiki_unless_it_is_an_event(recipe_id: str) -> None:
    recipe = DATASET.recipes[recipe_id]
    key = dataset_key(DATASET, recipe)
    if key in WIKI_KEYS:
        assert not is_event(recipe)
    else:
        assert is_event(recipe), describe(key)


def test_wiki_recording_is_complete() -> None:
    facilities = {r["facility"] for r in CRAFTS}
    assert len(CRAFTS) >= 290
    assert {"Reactor Crucible", "Purification Unit", "Planting Unit"} <= facilities


def test_event_recipes_are_flagged_in_the_dataset() -> None:
    """Every recipe the wiki marks ``event`` carries the flag, and no other does (RCP-06)."""
    assert DATASET.recipes["furnance_activity_xiranite_nugget_1"].event is True
    assert DATASET.recipes["dismantler_xiranenr_grass_2_1"].event is True
    assert DATASET.recipes["furnance_iron_nugget_1"].event is False
    for recipe_id, recipe in DATASET.recipes.items():
        assert recipe.event == is_event(recipe), recipe_id
    wiki_events = {wiki_key(r) for r in WIKI if r["event"]}
    for recipe in DATASET.recipes.values():
        if dataset_key(DATASET, recipe) in wiki_events:
            assert recipe.event, recipe.id
