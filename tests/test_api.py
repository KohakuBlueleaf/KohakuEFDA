"""The run API: create a run, run stages with parameters, tail events, rerun from a checkpoint."""

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from kohakuefda.layout.engine import LAYOUT_DEFAULTS
from kohakuefda.serve.server import serve

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
FIXTURES = ROOT / "tests" / "fixtures"
TIMEOUT = 180.0


def _request(url: str, body: dict | None = None) -> tuple[int, dict | list]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"} if data else {}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("workspace")


@pytest.fixture(scope="module")
def base_url(workspace: Path):
    server = serve(workspace, DATA_ROOT, port=0, workspace=workspace)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _wait(base_url: str, run_id: str, stage: str) -> dict:
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        _, summary = _request(f"{base_url}/api/runs/{run_id}")
        state = summary["stages"][stage]
        if state["status"] in ("done", "failed", "cancelled"):
            return summary
        time.sleep(0.2)
    raise AssertionError(f"stage {stage} did not finish")


def test_meta_examples_and_params(base_url: str) -> None:
    status, meta = _request(f"{base_url}/api/meta")
    assert status == 200
    assert meta["stages"] == ["plan", "netlist", "layout", "verify"]
    assert any(b["id"] == "sky_king_flats" for b in meta["basements"])
    status, examples = _request(f"{base_url}/api/examples")
    assert status == 200
    assert {e["name"] for e in examples} == {
        "valley_battery",
        "wuling_hetonite",
        "gas_xiranite",
    }
    status, params = _request(f"{base_url}/api/params")
    assert params["layout"]["spread_attempts"] == LAYOUT_DEFAULTS["spread_attempts"]
    assert params["layout"]["workers"] == LAYOUT_DEFAULTS["workers"]
    assert "bridge_cost" in params["layout"]


def test_scenario_toml_round_trip(base_url: str) -> None:
    text = (FIXTURES / "scenario_valley_battery.toml").read_text(encoding="utf-8")
    status, parsed = _request(f"{base_url}/api/scenario/parse", {"toml": text})
    assert status == 200
    status, back = _request(f"{base_url}/api/scenario/toml", parsed["scenario"])
    assert status == 200
    status, again = _request(f"{base_url}/api/scenario/parse", {"toml": back["toml"]})
    assert again["scenario"] == parsed["scenario"]
    status, error = _request(f"{base_url}/api/scenario/parse", {"toml": "= nope"})
    assert status == 400 and "error" in error


def test_run_stage_by_stage_with_checkpoints(base_url: str, workspace: Path) -> None:
    text = (FIXTURES / "scenario_valley_battery.toml").read_text(encoding="utf-8")
    _, parsed = _request(f"{base_url}/api/scenario/parse", {"toml": text})
    status, run = _request(f"{base_url}/api/runs", parsed["scenario"])
    assert status == 201
    run_id = run["id"]
    assert all(s["status"] == "idle" for s in run["stages"].values())

    status, error = _request(f"{base_url}/api/runs/{run_id}/stages/layout", {})
    assert status == 409 and "plan" in error["error"]

    status, queued = _request(
        f"{base_url}/api/runs/{run_id}/stages/plan", {"through": "netlist"}
    )
    assert status == 202 and queued["queued"] == ["plan", "netlist"]
    summary = _wait(base_url, run_id, "netlist")
    assert summary["stages"]["plan"]["status"] == "done"
    assert summary["stages"]["netlist"]["status"] == "done"
    assert "plan" in summary["artifacts"] and "netlist" in summary["artifacts"]

    status, queued = _request(
        f"{base_url}/api/runs/{run_id}/stages/layout",
        {"params": {"workers": 1, "frame_every": 20}, "through": "verify"},
    )
    assert status == 202
    summary = _wait(base_url, run_id, "verify")
    assert summary["stages"]["layout"]["params"]["workers"] == 1
    assert summary["stages"]["layout"]["status"] == "done"
    assert summary["stages"]["verify"]["status"] == "done"
    assert summary["frames"]["layout"] >= 11

    status, report = _request(f"{base_url}/api/runs/{run_id}/artifacts/report")
    assert status == 200
    errors = [f for f in report["findings"] if f["severity"] == "error"]
    assert not errors, errors
    status, placement = _request(f"{base_url}/api/runs/{run_id}/artifacts/placement")
    assert status == 200 and placement["blocks"]
    status, frames = _request(f"{base_url}/api/runs/{run_id}/frames/layout")
    assert frames[0]["kind"] == "catalogue" and frames[-1]["kind"] == "final"
    assert {f["kind"] for f in frames} >= {"catalogue", "build", "final"}

    status, events = _request(f"{base_url}/api/runs/{run_id}/events?once=1")
    assert status == 200
    kinds = {(e["kind"], e["stage"]) for e in events}
    assert ("stage", "verify") in kinds and ("frame", "layout") in kinds
    assert events[-1]["seq"] == len(events)

    directory = workspace / "runs" / run_id
    assert (directory / "layout.json").is_file()
    assert (directory / "placement.json").is_file()
    assert (directory / "frames" / "layout.json").is_file()
    assert (directory / "scenario.toml").is_file()


def test_rerun_layout_with_other_settings_clears_later_stages(base_url: str) -> None:
    _, runs = _request(f"{base_url}/api/runs")
    run_id = next(r["id"] for r in runs if r["stages"]["verify"]["status"] == "done")
    _, before = _request(f"{base_url}/api/runs/{run_id}/artifacts/layout")
    status, queued = _request(
        f"{base_url}/api/runs/{run_id}/stages/layout",
        {"params": {"turn_cost": 0.5, "spread_gap": 1}},
    )
    assert status == 202 and queued["queued"] == ["layout"]
    assert queued["run"]["stages"]["verify"]["status"] == "idle"
    assert "report" not in queued["run"]["artifacts"]
    summary = _wait(base_url, run_id, "layout")
    assert summary["stages"]["layout"]["status"] == "done"
    assert summary["stages"]["layout"]["params"]["turn_cost"] == 0.5
    assert summary["stages"]["layout"]["params"]["spread_gap"] == 1
    _, after = _request(f"{base_url}/api/runs/{run_id}/artifacts/layout")
    assert after["width"] == before["width"]
    status, _ = _request(
        f"{base_url}/api/runs/{run_id}/stages/layout", {"params": {"nope": 1}}
    )
    assert status == 400


def test_cancel_stops_a_running_layout(base_url: str) -> None:
    text = (FIXTURES / "scenario_basic.toml").read_text(encoding="utf-8")
    _, parsed = _request(f"{base_url}/api/scenario/parse", {"toml": text})
    _, run = _request(f"{base_url}/api/runs", parsed["scenario"])
    run_id = run["id"]
    _request(f"{base_url}/api/runs/{run_id}/stages/plan", {"through": "netlist"})
    _wait(base_url, run_id, "netlist")
    _request(
        f"{base_url}/api/runs/{run_id}/stages/layout",
        {
            "params": {"workers": 1, "frame_every": 1000},
            "through": "verify",
        },
    )
    time.sleep(0.5)
    status, summary = _request(f"{base_url}/api/runs/{run_id}/cancel", {})
    assert status == 200
    summary = _wait(base_url, run_id, "layout")
    assert summary["stages"]["layout"]["status"] == "cancelled"
    assert summary["stages"]["verify"]["status"] == "idle"


def test_requirements_outcomes_icons_and_delete(base_url: str, workspace: Path) -> None:
    text = (FIXTURES / "scenario_valley_battery.toml").read_text(encoding="utf-8")
    _, parsed = _request(f"{base_url}/api/scenario/parse", {"toml": text})
    status, needs = _request(f"{base_url}/api/requirements", parsed["scenario"])
    assert status == 200 and "item_quartz_sand" in needs["natural"]
    assert "gathered" in needs
    _, run = _request(f"{base_url}/api/runs", parsed["scenario"])
    run_id = run["id"]
    assert _request(f"{base_url}/api/runs/{run_id}/outcomes")[0] == 404
    _request(f"{base_url}/api/runs/{run_id}/stages/plan", {})
    _wait(base_url, run_id, "plan")
    status, found = _request(f"{base_url}/api/runs/{run_id}/outcomes")
    assert status == 200
    delivered = next(o for o in found if o["kind"] == "delivered")
    assert delivered["item_id"] == "item_proc_battery_1"
    assert all("product_id" in n for n in delivered["next"])
    status, choices = _request(f"{base_url}/api/runs/{run_id}/alternatives")
    assert status == 200
    assert set(choices) == {"alternatives", "bannable"}
    assert all("recipes" in a and "scenario" in a for a in choices["alternatives"])
    status, icons = _request(f"{base_url}/api/icons")
    assert status == 200 and set(icons) >= {"items", "machines", "logistics", "missing"}
    assert _get_status(f"{base_url}/icons/items/nothing.png") == 404
    assert _get_status(f"{base_url}/icons/items/..%2F..%2Fdataset.json") == 404
    request = urllib.request.Request(f"{base_url}/api/runs/{run_id}", method="DELETE")
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.status == 200
    assert _request(f"{base_url}/api/runs/{run_id}")[0] == 404
    assert not (workspace / "runs" / run_id).exists()


def _get_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_unknown_routes_and_bad_bodies(base_url: str) -> None:
    assert _request(f"{base_url}/api/runs/nope")[0] == 404
    assert _request(f"{base_url}/api/nothing")[0] == 404
    status, error = _request(f"{base_url}/api/runs", {"targets": {}})
    assert status == 400 and "scenario" in error["error"]
