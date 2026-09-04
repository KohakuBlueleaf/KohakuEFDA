"""Recorded wiki recipe modules against a dataset: keys, name normalisation, differences.

A wiki recipe is a dict as recorded by ``scripts/dev/wiki_recipes.py``: ``facility``, ``mode``,
``time``, ``environment``, ``event`` and ``ingredients`` / ``products`` stacks of ``item`` and
``count``. Recipes match on facility name and the base names and counts of their stacks, so
filled containers compare whatever suffix each source appends.
"""

import json
import re
from pathlib import Path
from typing import NamedTuple

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.recipes import Recipe

EVENT_MARK = "activity"
POWER_MODE = "Power"
SUFFIX_RE = re.compile(r"\s+[\(\[][^()\[\]]*[\)\]]$")
Stacks = tuple[tuple[str, int], ...]
Key = tuple[str, Stacks, Stacks]


class Difference(NamedTuple):
    """One disagreement: ``kind`` is wiki_only, dataset_only, time, env or fuel."""

    kind: str
    subject: str
    detail: str


def base_name(name: str) -> str:
    """The name without a bracketed suffix, with plural seeds made singular."""
    plain = SUFFIX_RE.sub("", name)
    return plain[:-1] if plain.endswith(" Seeds") else plain


def env_name(env: str | None) -> str:
    return (env or "").lower().removesuffix(" env").strip()


def is_event(recipe: Recipe) -> bool:
    """Whether a dataset recipe belongs to a limited-time event: its id or an item says so."""
    return EVENT_MARK in recipe.id or any(
        EVENT_MARK in s.item_id for s in recipe.inputs + recipe.outputs
    )


def load_wiki(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["recipes"]


def _stacks(stacks: list[tuple[str, int]]) -> Stacks:
    return tuple(sorted((base_name(name), count) for name, count in stacks))


def wiki_key(recipe: dict) -> Key:
    return (
        recipe["facility"],
        _stacks([(s["item"], int(s["count"])) for s in recipe["ingredients"]]),
        _stacks([(s["item"], int(s["count"])) for s in recipe["products"]]),
    )


def dataset_key(dataset: Dataset, recipe: Recipe) -> Key:
    return (
        dataset.machines[recipe.machine_id].names.en,
        _stacks([(dataset.items[s.item_id].names.en, s.count) for s in recipe.inputs]),
        _stacks([(dataset.items[s.item_id].names.en, s.count) for s in recipe.outputs]),
    )


def describe(key: Key) -> str:
    inputs = " + ".join(f"{count} {name}" for name, count in key[1])
    outputs = " + ".join(f"{count} {name}" for name, count in key[2])
    return f"{key[0]}: {inputs} -> {outputs}"


def crafting_recipes(wiki: list[dict]) -> list[dict]:
    """Wiki recipes a factory can run today: no event recipes, no Thermal Bank fuel rows."""
    return [r for r in wiki if not r["event"] and r["mode"] != POWER_MODE]


def dataset_index(dataset: Dataset) -> dict[Key, Recipe]:
    return {dataset_key(dataset, r): r for r in dataset.recipes.values()}


def recipe_differences(
    dataset: Dataset, wiki_recipe: dict, mine: Recipe | None
) -> list[Difference]:
    """Why one wiki recipe and its dataset counterpart disagree (empty when they agree)."""
    key = wiki_key(wiki_recipe)
    if mine is None:
        return [
            Difference(
                "wiki_only",
                describe(key),
                f"{wiki_recipe['time']}s {wiki_recipe['mode']}",
            )
        ]
    out: list[Difference] = []
    if mine.seconds != wiki_recipe["time"]:
        out.append(
            Difference(
                "time", mine.id, f"dataset {mine.seconds}s, wiki {wiki_recipe['time']}s"
            )
        )
    wanted = env_name(wiki_recipe["environment"])
    if wanted and wanted != env_name(mine.env):
        out.append(Difference("env", mine.id, f"dataset {mine.env!r}, wiki {wanted!r}"))
    return out


def compare(dataset: Dataset, wiki: list[dict]) -> list[Difference]:
    """Every difference between the recorded wiki and the dataset, both directions."""
    ours = dataset_index(dataset)
    wiki_keys: set[Key] = set()
    out: list[Difference] = []
    for recipe in crafting_recipes(wiki):
        key = wiki_key(recipe)
        wiki_keys.add(key)
        out += recipe_differences(dataset, recipe, ours.get(key))
    for key, mine in ours.items():
        if key not in wiki_keys and not is_event(mine):
            out.append(Difference("dataset_only", mine.id, describe(key)))
    return out
