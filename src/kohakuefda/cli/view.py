"""``kohakuefda serve`` and its alias ``view``: the web application over a directory."""

import logging
import socket
import webbrowser
from pathlib import Path

import typer
from rich.console import Console

from kohakuefda.cli.data import DEFAULT_ROOT
from kohakuefda.serve.server import ANY_HOST, DEFAULT_HOST, WEB_DIST, serve

log = logging.getLogger(__name__)
console = Console()


def view_cmd(
    directory: Path = typer.Argument(
        Path("out"),
        help="Directory with JSON artifacts; runs are kept under <dir>/runs/.",
    ),
    host: str = typer.Option(
        DEFAULT_HOST,
        "--host",
        help="Interface to bind; 0.0.0.0 listens on every interface.",
    ),
    port: int = typer.Option(
        8765, "--port", help="Port to listen on (0 for any free port)."
    ),
    open_browser: bool = typer.Option(False, "--open", help="Open the browser."),
    workers: int = typer.Option(1, "--workers", help="Stages that may run at once."),
    no_api: bool = typer.Option(
        False, "--no-api", help="Serve the artifacts only, without the run API."
    ),
    version: str = typer.Option("", "--version", "-v", help="Dataset version id."),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
) -> None:
    """Serve the web app: the viewer, the directory's artifacts, and the stage-by-stage run API."""
    if not (WEB_DIST / "index.html").is_file():
        console.print(
            "[red]viewer bundle missing[/]: run 'npm install && npm run build' in src/kohakuefda-viewer"
        )
        raise typer.Exit(code=2)
    directory.mkdir(parents=True, exist_ok=True)
    server = serve(
        directory,
        root,
        version,
        port,
        api=not no_api,
        workspace=None if no_api else directory,
        workers=workers,
        host=host,
    )
    bound = server.server_address[1]
    url = f"http://{DEFAULT_HOST if host == ANY_HOST else host}:{bound}/"
    console.print(f"serving [bold]{directory}[/] at {url} (Ctrl+C to stop)")
    if host == ANY_HOST:
        console.print(
            f"listening on every interface: http://{socket.gethostname()}:{bound}/"
        )
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("interrupted; shutting down")
    finally:
        server.server_close()
