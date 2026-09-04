"""The viewer server: artifact index, artifact files, dataset, bundle, and path containment."""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from kohakuefda.cli.view import WEB_DIST, serve
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.planner import plan

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("artifacts")
    dataset = Dataset.load(DATA_ROOT / "1.5.3@9764758-3" / "dataset.json")
    scenario = Scenario.from_toml(
        ROOT / "tests" / "fixtures" / "scenario_valley_battery.toml"
    )
    plan(dataset, scenario).save(directory / "plan.json")
    (directory / "notes.txt").write_text("not served", encoding="utf-8")
    return directory


@pytest.fixture(scope="module")
def base_url(artifacts: Path):
    server = serve(artifacts, DATA_ROOT, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_index_lists_only_artifact_files(base_url: str) -> None:
    status, body = _get(f"{base_url}/artifacts/index.json")
    assert status == 200
    index = json.loads(body)
    assert index["files"] == ["plan.json"]
    assert index["dataset"] == "dataset.json"


def test_artifacts_and_dataset_are_served(base_url: str) -> None:
    status, body = _get(f"{base_url}/artifacts/plan.json")
    assert status == 200
    loaded = json.loads(body)
    status, body = _get(f"{base_url}/dataset.json")
    assert status == 200
    assert json.loads(body)["version"]["id"] == loaded["dataset_version"]


def test_files_outside_the_directory_are_refused(base_url: str) -> None:
    assert _get(f"{base_url}/artifacts/notes.txt")[0] == 404
    assert _get(f"{base_url}/artifacts/..%2Fpyproject.toml")[0] == 404
    assert _get(f"{base_url}/artifacts/missing.json")[0] == 404


def test_bundle_is_served(base_url: str) -> None:
    if not (WEB_DIST / "index.html").is_file():
        pytest.skip("viewer bundle not built")
    status, body = _get(f"{base_url}/")
    assert status == 200
    assert b'id="app"' in body
