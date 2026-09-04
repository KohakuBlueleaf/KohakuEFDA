"""Hand-maintained natural resources (``static/resources.json``) → item id → source kind."""

import json
from importlib import resources


def build_resources() -> dict[str, str]:
    text = (
        resources.files("kohakuefda.data.static")
        .joinpath("resources.json")
        .read_text("utf-8")
    )
    return dict(json.loads(text)["resources"])
