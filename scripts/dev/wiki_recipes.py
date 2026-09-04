"""Record the wiki's recipe modules and diff them against the dataset.

``python scripts/dev/wiki_recipes.py fetch`` downloads every ``Module:Recipe/<facility>`` data
module from endfield.wiki.gg, parses the Lua tables and writes
``tests/fixtures/wiki_recipes.json``. ``python scripts/dev/wiki_recipes.py diff [dataset.json]``
prints every difference ``kohakuefda.data.reference.compare`` finds and exits 1 when there is one.
"""

import json
import re
import sys
from pathlib import Path

import httpx

from kohakuefda.data.reference import compare, load_wiki
from kohakuefda.model.dataset import Dataset

API = "https://endfield.wiki.gg/api.php"
HEADERS = {
    "User-Agent": "KohakuEFDA/0.0.1 (+https://github.com/KohakuBlueleaf/KohakuEFDA)"
}
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "wiki_recipes.json"
DEFAULT_DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
MODULES = [
    "Refining_Unit",
    "Shredding_Unit",
    "Fitting_Unit",
    "Moulding_Unit",
    "Planting_Unit",
    "Seed-Picking_Unit",
    "Gearing_Unit",
    "Filling_Unit",
    "Packaging_Unit",
    "Grinding_Unit",
    "Reactor_Crucible",
    "Expanded_Crucible",
    "Forge_of_the_Sky",
    "Separating_Unit",
    "Purification_Unit",
    "Fluid-Gas_Transmuting_Unit",
    "Solid-Gas_Transmuting_Unit",
    "Gas_Reactor_Globe",
    "Thermal_Bank",
]
RECIPE_RE = re.compile(r"\{\s*time\s*=(.*?)\n\},", re.DOTALL)
FIELD_RE = re.compile(r"(\w+)\s*=\s*(\"[^\"]*\"|\d+|true|false)")
STACK_RE = re.compile(r"\{\s*item\s*=\s*\"([^\"]+)\"\s*,\s*count\s*=\s*(\d+)\s*\}")
LIST_RE = re.compile(r"(ingredients|products)\s*=\s*\{(.*?)\}\s*,\s*\n", re.DOTALL)


def module_text(client: httpx.Client, module: str) -> str:
    response = client.get(
        API,
        params={
            "action": "query",
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content",
            "format": "json",
            "titles": f"Module:Recipe/{module}",
        },
    )
    response.raise_for_status()
    for page in response.json()["query"]["pages"].values():
        revisions = page.get("revisions") or [{}]
        return revisions[0].get("slots", {}).get("main", {}).get("*", "")
    return ""


def parse_module(text: str) -> list[dict]:
    """Every ``{ time = ..., ingredients = {...}, products = {...}, ... }`` entry as a dict."""
    out: list[dict] = []
    for match in RECIPE_RE.finditer(text):
        body = "time =" + match.group(1) + "\n"
        lists = {
            name: [
                {"item": item, "count": int(count)}
                for item, count in STACK_RE.findall(inner)
            ]
            for name, inner in LIST_RE.findall(body)
        }
        scalars: dict[str, object] = {}
        for key, value in FIELD_RE.findall(LIST_RE.sub("", body)):
            if value.startswith('"'):
                scalars[key] = value.strip('"')
            elif value in ("true", "false"):
                scalars[key] = value == "true"
            else:
                scalars[key] = int(value)
        out.append(
            {
                "facility": scalars.get("facility", ""),
                "mode": scalars.get("mode", ""),
                "time": scalars.get("time", 0),
                "environment": scalars.get("enviroment", ""),
                "event": bool(scalars.get("event", False)),
                "ingredients": lists.get("ingredients", []),
                "products": lists.get("products", []),
            }
        )
    return out


def fetch() -> None:
    recipes: list[dict] = []
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        for module in MODULES:
            parsed = parse_module(module_text(client, module))
            print(f"{module}: {len(parsed)} recipes")
            recipes.extend(parsed)
    FIXTURE.write_text(
        json.dumps({"source": API, "recipes": recipes}, ensure_ascii=False, indent=1)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(recipes)} recipes to {FIXTURE}")


def diff(dataset_file: Path) -> int:
    dataset = Dataset.load(dataset_file)
    differences = compare(dataset, load_wiki(FIXTURE))
    for kind, subject, detail in differences:
        print(f"{kind:<13}{subject}: {detail}")
    print(f"{len(differences)} differences")
    return 1 if differences else 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "diff"
    if command == "fetch":
        fetch()
    else:
        sys.exit(diff(Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DATASET))
