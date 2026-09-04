"""The scenario: the only inputs a user provides."""

import tomllib
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Literal

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.basement import Region
from kohakuefda.model.rates import Rate

UNLIMITED = "unlimited"
TargetGoal = Literal["min", "max"]
TARGET_MIN: TargetGoal = "min"
TARGET_MAX: TargetGoal = "max"
TargetSpec = Rate | TargetGoal
SupplyDefault = Literal["plenty", "none"]
ActivationMode = Literal["built", "duty"]
DepotMode = Literal["bus", "core"]


class PlanMode(StrEnum):
    AREA = "area"
    MACHINES = "machines"
    BALANCED = "balanced"


class BasementRef(EfdaModel):
    """Which basement the line is built in and how far it is upgraded."""

    region: Region
    basement_id: str
    level: int = 1
    depot_level: int = 1


def goal_of(spec: TargetSpec) -> TargetGoal | None:
    """``min`` or ``max`` for a rate-free target, ``None`` for a rate."""
    return spec if isinstance(spec, str) else None


def _toml_value(value: Fraction | str | None) -> str:
    if value is None:
        return f'"{UNLIMITED}"'
    if isinstance(value, str):
        return f'"{value}"'
    if value.denominator == 1:
        return str(value.numerator)
    return f'"{value}"'


class Scenario(EfdaModel):
    """Supply rates, targets, basement, mode and what may be used; everything else is derived.

    A target is a rate per minute, ``"min"`` (the smallest whole-machine line) or ``"max"`` (as
    much as the supply and the ``area_fill`` budget allow). ``gas``, ``liquids``, ``events`` and
    ``banned_machines`` filter recipes. Natural resources are plenty unless listed in
    ``supply`` (``natural_default``, ``gas_default``; game-knowledge RES-01). ``activation``
    charges a transmuter's fluid per built machine or per duty (ACT-03). ``depot`` puts solid
    lanes on Depot Bus bricks (``bus``) or on the Automation-Core's ports first (``core``)
    (DEP-02, DEP-06).
    """

    supply: dict[str, Rate | None] = {}
    targets: dict[str, TargetSpec] = {}
    basement: BasementRef
    mode: PlanMode = PlanMode.BALANCED
    mixed_lanes: bool = True
    gas: bool = True
    liquids: bool = True
    events: bool = False
    banned_machines: list[str] = []
    area_fill: float | None = None
    natural_default: SupplyDefault = "plenty"
    gas_default: SupplyDefault = "none"
    activation: ActivationMode = "built"
    depot: DepotMode = "bus"
    core: bool = False
    recipe_overrides: dict[str, str] = {}

    @classmethod
    def from_toml_text(cls, text: str) -> "Scenario":
        """Parse ``scenario.toml`` content; ``supply.<item> = "unlimited"`` maps to ``None``."""
        raw = tomllib.loads(text)
        supply = {
            k: (None if v == UNLIMITED else v) for k, v in raw.get("supply", {}).items()
        }
        return cls(
            supply=supply,
            targets=raw.get("targets", {}),
            basement=BasementRef(**raw["basement"]),
            mode=raw.get("mode", PlanMode.BALANCED),
            mixed_lanes=raw.get("mixed_lanes", True),
            gas=raw.get("gas", True),
            liquids=raw.get("liquids", True),
            events=raw.get("events", False),
            banned_machines=list(raw.get("banned_machines", [])),
            area_fill=raw.get("area_fill"),
            natural_default=raw.get("natural_default", "plenty"),
            gas_default=raw.get("gas_default", "none"),
            activation=raw.get("activation", "built"),
            depot=raw.get("depot", "bus"),
            core=raw.get("core", False),
            recipe_overrides=raw.get("recipe_overrides", {}),
        )

    @classmethod
    def from_toml(cls, path: Path) -> "Scenario":
        return cls.from_toml_text(path.read_text(encoding="utf-8"))

    def to_toml(self) -> str:
        """The scenario as TOML text that ``from_toml_text`` reads back unchanged."""
        lines = [
            f'mode = "{self.mode.value}"',
            f"mixed_lanes = {str(self.mixed_lanes).lower()}",
            f"gas = {str(self.gas).lower()}",
            f"liquids = {str(self.liquids).lower()}",
            f"events = {str(self.events).lower()}",
            f'natural_default = "{self.natural_default}"',
            f'gas_default = "{self.gas_default}"',
            f'activation = "{self.activation}"',
            f'depot = "{self.depot}"',
            f"core = {str(self.core).lower()}",
        ]
        if self.banned_machines:
            banned = ", ".join(f'"{m}"' for m in self.banned_machines)
            lines.append(f"banned_machines = [{banned}]")
        if self.area_fill is not None:
            lines.append(f"area_fill = {self.area_fill}")
        lines += ["", "[supply]"]
        lines += [f"{item} = {_toml_value(rate)}" for item, rate in self.supply.items()]
        lines += ["", "[targets]"]
        lines += [
            f"{item} = {_toml_value(spec)}" for item, spec in self.targets.items()
        ]
        lines += [
            "",
            "[basement]",
            f'region = "{self.basement.region.value}"',
            f'basement_id = "{self.basement.basement_id}"',
            f"level = {self.basement.level}",
            f"depot_level = {self.basement.depot_level}",
        ]
        if self.recipe_overrides:
            lines += ["", "[recipe_overrides]"]
            lines += [
                f'{item} = "{recipe}"' for item, recipe in self.recipe_overrides.items()
            ]
        return "\n".join(lines) + "\n"
