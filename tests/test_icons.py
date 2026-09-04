"""Icon fetching through a recorded wiki transport: titles, batches, downloads, the index."""

import json
from pathlib import Path

import httpx
import pytest

from kohakuefda.data.icons import (
    fetch_icons,
    icon_titles,
    icons_dir,
    load_icon_index,
    query_files,
)
from kohakuefda.model.dataset import Dataset

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
KNOWN = {
    "originium ore": "https://images.test/Originium_Ore.png",
    "grinder": "https://images.test/Grinder.png",
}


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


class Wiki:
    """A wiki that knows two files and serves their bytes; counts every request."""

    def __init__(self) -> None:
        self.queries = 0
        self.downloads = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "images.test":
            self.downloads += 1
            return httpx.Response(200, content=PNG)
        self.queries += 1
        titles = request.url.params["titles"].split("|")
        assert len(titles) <= 50
        pages = {}
        normalized = []
        for index, title in enumerate(titles):
            name = title.removeprefix("File:").removesuffix(".png")
            canonical = name[:1].upper() + name[1:]
            if canonical != name:
                normalized.append({"from": title, "to": f"File:{canonical}.png"})
            key = canonical.lower()
            if key in KNOWN:
                pages[str(index + 1)] = {
                    "title": f"File:{canonical}.png",
                    "imageinfo": [{"url": KNOWN[key]}],
                }
            else:
                pages[str(-index - 1)] = {
                    "title": f"File:{canonical}.png",
                    "missing": "",
                }
        return httpx.Response(
            200, json={"query": {"normalized": normalized, "pages": pages}}
        )


def test_icon_titles_come_from_english_names(dataset: Dataset) -> None:
    titles = icon_titles(dataset)
    assert titles[("items", "item_originium_ore")][0] == "Originium Ore"
    assert ("machines", "grinder_1") in titles or any(
        k[0] == "machines" for k in titles
    )
    assert all(kind in ("items", "machines", "logistics") for kind, _ in titles)


def test_query_files_batches_and_maps_normalised_titles() -> None:
    wiki = Wiki()
    with httpx.Client(transport=httpx.MockTransport(wiki)) as client:
        found = query_files(client, ["originium ore", "Grinder", "Nothing Here"] * 30)
    assert found == {
        "originium ore": KNOWN["originium ore"],
        "grinder": KNOWN["grinder"],
    }
    assert wiki.queries == 1


def test_fetch_icons_downloads_once_and_records_misses(
    dataset: Dataset, tmp_path: Path
) -> None:
    wiki = Wiki()
    with httpx.Client(transport=httpx.MockTransport(wiki)) as client:
        index = fetch_icons(client, dataset, tmp_path)
        assert index["items"]["item_originium_ore"] == "items/item_originium_ore.png"
        file = icons_dir(tmp_path) / "items" / "item_originium_ore.png"
        assert file.read_bytes() == PNG
        assert wiki.downloads == len(index["items"]) + len(index["machines"]) + len(
            index["logistics"]
        )
        assert "items/item_quartz_sand" in index["missing"]
        assert "items/item_originium_ore" not in index["missing"]
        stored = json.loads((icons_dir(tmp_path) / "index.json").read_text("utf-8"))
        assert stored == index
        assert load_icon_index(tmp_path) == index
        downloads = wiki.downloads
        fetch_icons(client, dataset, tmp_path)
        assert wiki.downloads == downloads
        fetch_icons(client, dataset, tmp_path, refresh=True)
        assert wiki.downloads == downloads * 2
