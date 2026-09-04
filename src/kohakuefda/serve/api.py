"""The JSON API over one dataset and one run manager.

``GET``: ``/api/meta``, ``/api/dataset``, ``/api/examples``, ``/api/params``, ``/api/icons``,
``/api/runs``, ``/api/runs/<id>``, ``/api/runs/<id>/artifacts/<name>``,
``/api/runs/<id>/frames/<stage>``, ``/api/runs/<id>/outcomes``,
``/api/runs/<id>/alternatives`` (other recipe paths and the machines that may be banned),
``/api/runs/<id>/events?since=N`` (the event stream; ``once=1`` returns the backlog as JSON).
``POST``: ``/api/runs`` (a scenario), ``/api/runs/<id>/stages/<stage>`` (``params``,
``through``), ``/api/runs/<id>/cancel``, ``/api/requirements`` (a scenario),
``/api/scenario/parse`` (``toml``), ``/api/scenario/toml`` (a scenario).
``DELETE``: ``/api/runs/<id>``. Every handler returns an HTTP status and a JSON body; bad
input is a 400 or 409 with ``{"error": ...}``.
"""

import logging
import tomllib
from importlib import resources
from pathlib import Path

from pydantic import ValidationError

from kohakuefda.data.icons import IconIndex
from kohakuefda.layout.stages import DEFAULTS, STAGES, StageError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import PlanMode, Scenario
from kohakuefda.plan.alternatives import alternatives, bannable
from kohakuefda.plan.outcomes import outcomes, requirements
from kohakuefda.serve.runs import RunError, RunManager

log = logging.getLogger(__name__)
Response = tuple[int, dict | list]
EXAMPLES_PACKAGE = "kohakuefda.data.static.examples"
RUNS_PREFIX = "/api/runs/"


class ApiError(ValueError):
    """A request the API rejects; the message goes to the client."""


def _scenario(payload: object) -> Scenario:
    if not isinstance(payload, dict):
        raise ApiError("the body must be a scenario object")
    try:
        return Scenario.model_validate(payload)
    except ValidationError as error:
        raise ApiError(f"invalid scenario: {error.errors()[0]['msg']}") from error


def example_scenarios() -> list[dict]:
    """The bundled example scenarios: name, TOML text and the parsed scenario."""
    out: list[dict] = []
    for entry in sorted(resources.files(EXAMPLES_PACKAGE).iterdir(), key=str):
        if entry.name.endswith(".toml"):
            text = entry.read_text(encoding="utf-8")
            out.append(
                {
                    "name": Path(entry.name).stem,
                    "toml": text,
                    "scenario": Scenario.from_toml_text(text).model_dump(mode="json"),
                }
            )
    return out


class Api:
    """Dispatches API paths to handlers over one dataset, one run manager and the icon index."""

    def __init__(self, dataset: Dataset, runs: RunManager, icons: IconIndex) -> None:
        self.dataset = dataset
        self.runs = runs
        self.icons = icons

    def meta(self) -> dict:
        basements = [
            {
                "id": b.id,
                "names": b.names.model_dump(),
                "region": b.region.value,
                "hub": b.hub,
                "square_by_level": {
                    str(level): list(square) if square else None
                    for level, square in b.square_by_level.items()
                },
                "depot_kind": b.depot.kind,
                "depot_levels": sorted(
                    b.depot.sections_by_level
                    if b.depot.kind == "laid"
                    else b.depot.segments_by_level
                ),
            }
            for b in self.dataset.basements.values()
        ]
        return {
            "version": self.dataset.version.id,
            "regions": ["valley4", "wuling"],
            "modes": [mode.value for mode in PlanMode],
            "stages": list(STAGES),
            "basements": basements,
        }

    def get(self, path: str, query: dict[str, str]) -> Response:
        try:
            return self._get(path, query)
        except (ApiError, RunError, StageError) as error:
            log.debug("GET %s -> 404: %s", path, error)
            return 404, {"error": str(error)}

    def _get(self, path: str, query: dict[str, str]) -> Response:
        if path == "/api/meta":
            return 200, self.meta()
        if path == "/api/dataset":
            return 200, self.dataset.model_dump(mode="json")
        if path == "/api/examples":
            return 200, example_scenarios()
        if path == "/api/params":
            return 200, DEFAULTS
        if path == "/api/icons":
            return 200, self.icons
        if path == "/api/runs":
            return 200, [run.summary() for run in self.runs.runs()]
        if path.startswith(RUNS_PREFIX):
            parts = path[len(RUNS_PREFIX) :].split("/")
            run = self.runs.require(parts[0])
            if len(parts) == 1:
                return 200, run.summary()
            if len(parts) == 3 and parts[1] == "artifacts":
                artifact = run.artifacts.get(parts[2])
                if artifact is None:
                    raise ApiError(f"no artifact {parts[2]!r} in run {run.id}")
                return 200, artifact.model_dump(mode="json")
            if len(parts) == 3 and parts[1] == "frames":
                if parts[2] not in run.frames:
                    raise ApiError(f"no frames for stage {parts[2]!r}")
                return 200, run.frames[parts[2]]
            if len(parts) == 2 and parts[1] == "outcomes":
                plan = run.artifacts.get("plan")
                if plan is None:
                    raise ApiError(f"run {run.id} has no plan yet")
                return 200, [
                    o.model_dump(mode="json")
                    for o in outcomes(self.dataset, run.scenario, plan)
                ]
            if len(parts) == 2 and parts[1] == "alternatives":
                plan = run.artifacts.get("plan")
                if plan is None:
                    raise ApiError(f"run {run.id} has no plan yet")
                return 200, {
                    "alternatives": [
                        a.model_dump(mode="json")
                        for a in alternatives(self.dataset, run.scenario, plan)
                    ],
                    "bannable": bannable(self.dataset, run.scenario, plan),
                }
            if len(parts) == 2 and parts[1] == "events":
                since = int(query.get("since", "0") or 0)
                return 200, run.events_since(since)
        return 404, {"error": "no such route"}

    def post(self, path: str, body: object) -> Response:
        try:
            return self._post(path, body)
        except (ApiError, StageError) as error:
            log.debug("POST %s -> 400: %s", path, error)
            return 400, {"error": str(error)}
        except RunError as error:
            log.debug("POST %s -> 409: %s", path, error)
            return 409, {"error": str(error)}

    def _post(self, path: str, body: object) -> Response:
        if path == "/api/runs":
            run = self.runs.create(_scenario(body))
            log.info("run %s created", run.id)
            return 201, run.summary()
        if path.startswith(RUNS_PREFIX):
            parts = path[len(RUNS_PREFIX) :].split("/")
            run = self.runs.require(parts[0])
            if len(parts) == 3 and parts[1] == "stages":
                payload = body if isinstance(body, dict) else {}
                params = payload.get("params") or {}
                if not isinstance(params, dict):
                    raise ApiError("params must be an object")
                through = payload.get("through")
                queued = self.runs.start(run.id, parts[2], params, through)
                return 202, {"queued": queued, "run": run.summary()}
            if len(parts) == 2 and parts[1] == "cancel":
                self.runs.cancel(run.id)
                return 200, run.summary()
            raise ApiError("no such route")
        if path == "/api/requirements":
            return 200, requirements(self.dataset, _scenario(body)).model_dump(
                mode="json"
            )
        if path == "/api/scenario/parse":
            if not isinstance(body, dict) or not isinstance(body.get("toml"), str):
                raise ApiError("the body must be an object with toml text")
            try:
                scenario = Scenario.from_toml_text(body["toml"])
            except (tomllib.TOMLDecodeError, KeyError, ValidationError) as error:
                raise ApiError(f"invalid scenario.toml: {error}") from error
            return 200, {"scenario": scenario.model_dump(mode="json")}
        if path == "/api/scenario/toml":
            return 200, {"toml": _scenario(body).to_toml()}
        return 404, {"error": "no such route"}

    def delete(self, path: str) -> Response:
        if path.startswith(RUNS_PREFIX):
            run_id = path[len(RUNS_PREFIX) :].strip("/")
            try:
                self.runs.delete(run_id)
            except RunError as error:
                return 404, {"error": str(error)}
            log.info("run %s deleted", run_id)
            return 200, {"deleted": run_id}
        return 404, {"error": "no such route"}
