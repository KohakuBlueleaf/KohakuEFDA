"""FactoryPowerPoleTable → pylon records.

Facts: game-knowledge COV-01 (``rangeExtend``), COV-05, COV-06, COV-08 (``autoConnectLength``,
``autoConnect``).
"""

from kohakuefda.data.normalize.tables import RawTables, as_int
from kohakuefda.model.power import Pylon


def build_pylons(tables: RawTables) -> dict[str, Pylon]:
    """Pylons and relays: coverage reach from ``rangeExtend.x``, cable reach, auto-connection."""
    out: dict[str, Pylon] = {}
    for machine_id, record in tables["FactoryPowerPoleTable"].items():
        extend = record.get("rangeExtend") or {}
        out[machine_id] = Pylon(
            machine_id=machine_id,
            reach=as_int(extend.get("x")),
            auto_connect_length=float(record.get("autoConnectLength") or 0),
            auto_connect=bool(record.get("autoConnect", False)),
            covers=bool(record.get("defaultEnableDiffuser", True)),
        )
    return out
