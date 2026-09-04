"""Traditional-Chinese names from endfield.wiki.gg infoboxes, keyed by English page title."""

import json
import logging
import re
from pathlib import Path

import httpx

from kohakuefda.data.sources import WIKI_API_URL

log = logging.getLogger(__name__)
BATCH = 50
CN_RE = re.compile(r"\|\s*cnname\s*=\s*([^\n|]+)")
TC_RE = re.compile(r"\|\s*tcname\s*=\s*([^\n|]+)")
WIKI_NAMES_FILE = "wiki-names.json"
ALIASES = {
    "Automation-Core": "Protocol Automation-Core (PAC)",
}


def title_candidates(name: str) -> list[str]:
    """Wiki page titles that may hold ``name``: the name itself, aliases, and spelling variants."""
    out = [name]
    if name in ALIASES:
        out.append(ALIASES[name])
    bracketed = name.replace("[", "(").replace("]", ")")
    if bracketed != name:
        out.append(bracketed)
    if name.endswith("Seeds"):
        out.append(name[:-1])
    return out


def fetch_wiki_names(
    client: httpx.Client, titles: list[str]
) -> dict[str, dict[str, str]]:
    """``{title: {"cn": ..., "tc": ...}}`` for every title whose page has an infobox."""
    out: dict[str, dict[str, str]] = {}
    for start in range(0, len(titles), BATCH):
        chunk = titles[start : start + BATCH]
        log.debug(
            "wiki names batch %d-%d of %d", start, start + len(chunk), len(titles)
        )
        params = {
            "action": "query",
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content",
            "redirects": "1",
            "format": "json",
            "titles": "|".join(chunk),
        }
        response = client.get(WIKI_API_URL, params=params)
        response.raise_for_status()
        query = response.json().get("query", {})
        redirected = {r["to"]: r["from"] for r in query.get("redirects", [])}
        for page in query.get("pages", {}).values():
            revisions = page.get("revisions")
            if not revisions:
                continue
            text = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            cn = CN_RE.search(text)
            tc = TC_RE.search(text)
            if cn or tc:
                title = redirected.get(page["title"], page["title"])
                out[title] = {
                    "cn": cn.group(1).strip() if cn else "",
                    "tc": tc.group(1).strip() if tc else "",
                }
    log.info("wiki names: %d of %d title(s) matched", len(out), len(titles))
    return out


def save_wiki_names(path: Path, names: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(names, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8"
    )


def load_wiki_names(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))
