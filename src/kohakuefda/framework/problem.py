"""Immutable problem capture and versioned content identities."""

import hashlib
import json

from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Plan
from kohakuefda.model.solver import Problem

RULES = "endfield-ports-v1"


def digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


def problem_of(dataset: Dataset, netlist: Netlist, plan: Plan | None = None) -> Problem:
    """Capture domain inputs without retaining mutable references from the caller."""
    if netlist.dataset_version != dataset.version.id:
        raise ValueError("netlist and dataset versions differ")
    if plan is not None and (
        plan.dataset_version != dataset.version.id or plan.scenario != netlist.scenario
    ):
        raise ValueError("plan does not belong to this netlist scenario/version")
    data = dataset.model_dump_json()
    nets = netlist.model_dump_json()
    planned = plan.model_dump_json() if plan else None
    return Problem(digest(RULES, data, nets, planned or ""), data, nets, planned, RULES)
