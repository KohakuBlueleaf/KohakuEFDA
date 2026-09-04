"""The HTTP server: the viewer bundle, the artifact files of a directory, the dataset, the
icons, the JSON API, and the run event stream.

Routes: ``/`` and static files from ``web_dist/``; ``/artifacts/index.json`` (the JSON and PNG
files of the artifact directory); ``/artifacts/<file>`` (files of that directory only);
``/dataset.json``; ``/icons/<kind>/<id>.png`` from the data root's icon store;
``/api/runs/<id>/events`` as Server-Sent Events unless ``once=1``; everything else under
``/api/`` goes to ``Api`` (``GET``, ``POST`` and ``DELETE``).
"""

import json
import logging
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from kohakuefda.data.icons import KINDS, icons_dir, load_icon_index
from kohakuefda.data.normalize.build import dataset_path
from kohakuefda.model.dataset import Dataset
from kohakuefda.serve.api import Api
from kohakuefda.serve.runs import RunManager

log = logging.getLogger(__name__)
WEB_DIST = Path(__file__).resolve().parent.parent / "web_dist"
ARTIFACT_PREFIX = "/artifacts/"
ICON_PREFIX = "/icons/"
API_PREFIX = "/api/"
ARTIFACT_SUFFIXES = {".json", ".png"}
CONTENT_TYPES = {".json": "application/json", ".png": "image/png"}
VERSIONED = ("plan.json", "layout.json", "netlist.json", "report.json")
MAX_BODY = 64 * 1024 * 1024
KEEP_ALIVE_SECONDS = 15.0
DEFAULT_HOST = "127.0.0.1"
ANY_HOST = "0.0.0.0"


class AppHandler(SimpleHTTPRequestHandler):
    """Static bundle, artifact files and their index, the dataset, icons, the API, streams."""

    def __init__(
        self,
        *args,
        artifacts: Path,
        dataset_file: Path,
        icons: Path,
        web_dist: Path,
        api: Api | None,
        **kwargs,
    ) -> None:
        self.artifacts = artifacts
        self.dataset_file = dataset_file
        self.icons = icons
        self.api = api
        super().__init__(*args, directory=str(web_dist), **kwargs)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        query = dict(parse_qsl(parts.query))
        if path.startswith(API_PREFIX):
            if self.api is None:
                self.send_error(HTTPStatus.NOT_FOUND)
            elif path.endswith("/events") and query.get("once") != "1":
                self._stream(path, query)
            else:
                status, payload = self.api.get(path, query)
                self._send_json(payload, status)
        elif path == ARTIFACT_PREFIX + "index.json":
            self._send_json(self._index())
        elif path.startswith(ARTIFACT_PREFIX):
            self._send_file(self._artifact(path[len(ARTIFACT_PREFIX) :]))
        elif path.startswith(ICON_PREFIX):
            self._send_file(self._icon(path[len(ICON_PREFIX) :]), cache=True)
        elif path == "/dataset.json":
            self._send_file(self.dataset_file)
        else:
            super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if self.api is None or not path.startswith(API_PREFIX):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            self._send_json({"error": "the body is not JSON"}, HTTPStatus.BAD_REQUEST)
            return
        status, payload = self.api.post(path, body)
        self._send_json(payload, status)

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        if self.api is None or not path.startswith(API_PREFIX):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        status, payload = self.api.delete(path)
        self._send_json(payload, status)

    def _stream(self, path: str, query: dict[str, str]) -> None:
        """Server-Sent Events: the backlog after ``since``, then every new event as it happens."""
        run_id = path[len(API_PREFIX) + len("runs/") : -len("/events")]
        run = self.api.runs.get(run_id)
        if run is None:
            self._send_json({"error": f"no run {run_id!r}"}, HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last = int(self.headers.get("Last-Event-ID") or query.get("since", "0") or 0)
        log.debug("event stream opened for run %s since seq %d", run_id, last)
        try:
            while True:
                events = run.events_since(last, KEEP_ALIVE_SECONDS)
                if not events:
                    self.wfile.write(b": keep-alive\n\n")
                for event in events:
                    line = json.dumps(event)
                    self.wfile.write(f"id: {event['seq']}\ndata: {line}\n\n".encode())
                    last = event["seq"]
                self.wfile.flush()
        except OSError:
            log.debug("event stream closed for run %s at seq %d", run_id, last)
            return

    def _index(self) -> dict:
        files = sorted(
            p.name
            for p in self.artifacts.iterdir()
            if p.is_file() and p.suffix in ARTIFACT_SUFFIXES
        )
        return {"files": files, "dataset": self.dataset_file.name}

    def _artifact(self, name: str) -> Path | None:
        candidate = (self.artifacts / name).resolve()
        if (
            candidate.parent != self.artifacts.resolve()
            or not candidate.is_file()
            or candidate.suffix not in ARTIFACT_SUFFIXES
        ):
            return None
        return candidate

    def _icon(self, name: str) -> Path | None:
        kind, _, file = name.partition("/")
        if kind not in KINDS or "/" in file or not file.endswith(".png"):
            return None
        candidate = (self.icons / kind / file).resolve()
        if candidate.parent != (self.icons / kind).resolve() or not candidate.is_file():
            return None
        return candidate

    def _send_file(self, path: Path | None, cache: bool = False) -> None:
        if path is None or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_bytes(
            path.read_bytes(),
            CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
            cache=cache,
        )

    def _send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        self._send_bytes(
            json.dumps(payload).encode("utf-8"), "application/json", status
        )

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: int = HTTPStatus.OK,
        cache: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        """Every request at DEBUG, so ``-vv`` shows what the browser is doing."""
        log.debug("%s %s", self.address_string(), format % args)


class AppServer(ThreadingHTTPServer):
    """The bound server plus the run manager it owns."""

    def __init__(
        self, address: tuple[str, int], handler, runs: RunManager | None
    ) -> None:
        super().__init__(address, handler)
        self.runs = runs

    def server_close(self) -> None:
        if self.runs is not None:
            self.runs.shutdown()
        super().server_close()


def newest_version(root: Path) -> str:
    candidates = sorted(p.name for p in root.iterdir() if (p / "dataset.json").exists())
    if not candidates:
        raise FileNotFoundError(f"no dataset under {root}")
    return candidates[-1]


def artifact_dataset(root: Path, artifacts: Path, version: str = "") -> Path:
    """The dataset file the artifacts were made with, else ``version``, else the newest."""
    if not version:
        for name in VERSIONED:
            file = artifacts / name
            if file.is_file():
                try:
                    version = json.loads(file.read_text(encoding="utf-8")).get(
                        "dataset_version", ""
                    )
                except ValueError:
                    version = ""
                if version:
                    break
    return dataset_path(root, version or newest_version(root))


def serve(
    artifacts: Path,
    root: Path = Path("data"),
    version: str = "",
    port: int = 0,
    web_dist: Path = WEB_DIST,
    api: bool = True,
    workspace: Path | None = None,
    workers: int = 1,
    host: str = DEFAULT_HOST,
) -> AppServer:
    """A bound, not yet running server; ``port`` 0 picks a free one, ``host``
    ``0.0.0.0`` listens on every interface.

    With ``api`` the dataset is loaded and a run manager keeps runs under
    ``workspace/runs/<id>/`` (in memory only when ``workspace`` is ``None``).
    """
    dataset_file = artifact_dataset(root, artifacts, version)
    runs: RunManager | None = None
    api_object: Api | None = None
    if api:
        dataset = Dataset.load(dataset_file)
        runs = RunManager(dataset, workspace, workers)
        api_object = Api(dataset, runs, load_icon_index(root))
    handler = partial(
        AppHandler,
        artifacts=artifacts.resolve(),
        dataset_file=dataset_file,
        icons=icons_dir(root).resolve(),
        web_dist=web_dist,
        api=api_object,
    )
    server = AppServer((host, port), handler, runs)
    log.info(
        "bound to %s:%d (api=%s, dataset %s)",
        host,
        server.server_address[1],
        api,
        dataset_file,
    )
    return server
