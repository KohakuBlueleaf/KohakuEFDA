"""The versioned dataset: everything the planner knows about the game."""

import json
from pathlib import Path

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.basement import Basement
from kohakuefda.model.items import Item, Phase
from kohakuefda.model.logistics import LogisticsConstants, LogisticsUnit
from kohakuefda.model.machines import Machine
from kohakuefda.model.names import Names
from kohakuefda.model.power import Pylon
from kohakuefda.model.recipes import Recipe
from kohakuefda.model.sinks import Activation, DumpSink

SCHEMA_VERSION = 3


class DatasetVersion(EfdaModel):
    """Game version and hotfix as published by the data source, e.g. ``1.5.3@9764758-3``."""

    id: str
    game_version: str
    hotfix: str
    source: str = "akedata"
    published_at: str = ""

    @classmethod
    def parse(
        cls, version_id: str, source: str = "akedata", published_at: str = ""
    ) -> "DatasetVersion":
        game_version, _, hotfix = version_id.partition("@")
        return cls(
            id=version_id,
            game_version=game_version,
            hotfix=hotfix,
            source=source,
            published_at=published_at,
        )


class Dataset(EfdaModel):
    """Items, machines, recipes, logistics, basements and tech names for one game version."""

    schema_version: int = SCHEMA_VERSION
    version: DatasetVersion
    items: dict[str, Item]
    machines: dict[str, Machine]
    recipes: dict[str, Recipe]
    logistics: dict[str, LogisticsUnit]
    constants: LogisticsConstants
    basements: dict[str, Basement]
    tech_names: dict[str, Names] = {}
    activations: dict[str, Activation] = {}
    dumps: dict[str, DumpSink] = {}
    env_gases: dict[str, str] = {}
    resources: dict[str, str] = {}
    pylons: dict[str, Pylon] = {}

    def is_resource(self, item_id: str) -> bool:
        """Whether the world supplies ``item_id`` (mining rigs, pumps, gas vents)."""
        return item_id in self.resources

    def is_gas(self, item_id: str) -> bool:
        return self.items[item_id].phase is Phase.GAS

    def dump_for(self, item_id: str) -> DumpSink | None:
        """The placeable dump sink that accepts ``item_id``, if any."""
        for sink in self.dumps.values():
            if not sink.fixed and item_id in sink.items:
                return sink
        return None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Dataset":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def recipes_for(self, item_id: str) -> list[Recipe]:
        """Recipes whose outputs include ``item_id``."""
        return [
            r
            for r in self.recipes.values()
            if any(s.item_id == item_id for s in r.outputs)
        ]

    def recipes_of(self, machine_id: str) -> list[Recipe]:
        return [r for r in self.recipes.values() if r.machine_id == machine_id]

    def output_ports(self, recipe: Recipe, item_id: str) -> list[int]:
        """Ports of ``recipe``'s machine that emit ``item_id``, using the item's phase."""
        return recipe.output_ports(item_id, self.items[item_id].phase.is_fluid)

    def input_ports(self, recipe: Recipe, item_id: str) -> list[int]:
        """Ports of ``recipe``'s machine that accept ``item_id``, using the item's phase."""
        return recipe.input_ports(item_id, self.items[item_id].phase.is_fluid)
