"""Transmuter, vaporizer and fluid-consume tables → activations, dump sinks and env gases."""

from fractions import Fraction

from kohakuefda.data.normalize.recipes import ENV_NAMES
from kohakuefda.data.normalize.tables import RawTables, as_int
from kohakuefda.model.sinks import Activation, DumpSink


def build_activations(tables: RawTables) -> dict[str, Activation]:
    out: dict[str, Activation] = {}
    for machine_id, record in tables["FactoryTransmuterTable"].items():
        out[machine_id] = Activation(
            machine_id=machine_id,
            item_id=record["consumeItem"],
            min_rate=Fraction(as_int(record["consumeRate"])),
            max_rate=Fraction(as_int(record["consumeRateUpperLimit"])),
        )
    return out


def build_env_gases(tables: RawTables) -> dict[str, str]:
    """Environment name → the gas a Gas Dispersing Unit needs to create it."""
    out: dict[str, str] = {}
    for record in tables["FactoryVaporizerTable"].values():
        for group in record.get("groups", []):
            env = ENV_NAMES.get(str(group.get("genEnv")))
            if env:
                out[env] = group["consumeItem"]
    return out


def build_dumps(tables: RawTables) -> dict[str, DumpSink]:
    out: dict[str, DumpSink] = {}
    for machine_id, record in tables["FactoryFluidConsumeTable"].items():
        out[machine_id] = DumpSink(
            machine_id=machine_id,
            items=list(record.get("liquidable", [])),
            rate_per_machine=Fraction(60000, as_int(record.get("msPerRound"), 2000)),
        )
    if tables.has("FactorySewageTreatImportTable"):
        for machine_id, record in tables["FactorySewageTreatImportTable"].items():
            out[machine_id] = DumpSink(
                machine_id=machine_id,
                items=list(record.get("liquidable", [])),
                rate_per_machine=Fraction(60000, as_int(record.get("msPerRound"), 500)),
                fixed=True,
            )
    return out
