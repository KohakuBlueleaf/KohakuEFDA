"""The project's logging: one format, one place to turn it on.

Format: ``[HH:MM:SS] [module.name] [LEVEL] message [field=value, ...]``, coloured per level on a
terminal that takes ANSI (DEBUG grey, INFO green, WARNING yellow, ERROR red, CRITICAL magenta).
Records carry structured fields through :class:`~kohakuefda.util.logger.EfdaLogger`, so a call
reads ``log.info("layout done", width=40, height=31)`` and the fields land at the end of the
line.

The library only ever calls ``logging.getLogger(__name__)``; nothing configures handlers on
import. An entry point — the CLI, the server, a script — calls :func:`setup` once, which is
idempotent and attaches a flushing stderr handler and, when asked, a file handler.
"""

import logging
import sys
from pathlib import Path

from kohakuefda.util.logger import EfdaLogger

ROOT = "kohakuefda"
FORMAT = "[{time}] [{name}] [{level}] {message}"
NAME_WIDTH = 26
COLOURS = {
    "DEBUG": "\033[90m",
    "INFO": "\033[92m",
    "WARNING": "\033[93m",
    "ERROR": "\033[91m",
    "CRITICAL": "\033[95m",
}
RESET = "\033[0m"
BUILTIN = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}
_handlers: list[logging.Handler] = []


def supports_colour(stream: object) -> bool:
    """Whether ANSI escapes reach the eye; on Windows this also turns them on."""
    if not getattr(stream, "isatty", None) or not stream.isatty():
        return False
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        return bool(kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7))
    except (AttributeError, OSError, ImportError):
        return False


class Formatter(logging.Formatter):
    """One line per record, with the fields the caller passed and an optional colour."""

    def __init__(self, colour: bool = True) -> None:
        super().__init__()
        self.colour = colour

    def format(self, record: logging.LogRecord) -> str:
        name = record.name
        if len(name) > NAME_WIDTH:
            name = "..." + name[-(NAME_WIDTH - 3) :]
        message = record.getMessage()
        fields = [
            f"{key}={value}"
            for key, value in record.__dict__.items()
            if key not in BUILTIN
        ]
        if fields:
            message = f"{message} [{', '.join(fields)}]"
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        line = FORMAT.format(
            time=self.formatTime(record, "%H:%M:%S"),
            name=name,
            level=record.levelname,
            message=message,
        )
        if self.colour and record.levelname in COLOURS:
            return f"{COLOURS[record.levelname]}{line}{RESET}"
        return line


class FlushingHandler(logging.StreamHandler):
    """A stream handler that flushes every record and survives a stream whose encoding
    cannot carry it — a Windows console in a legacy code page renders ``×`` and CJK as
    replacement characters instead of losing the line."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record) + self.terminator
            try:
                self.stream.write(line)
            except UnicodeEncodeError:
                encoding = getattr(self.stream, "encoding", None) or "ascii"
                self.stream.write(line.encode(encoding, "replace").decode(encoding))
            self.flush()
        except RecursionError:
            raise
        except Exception:  # noqa: BLE001 - logging must never take the program down
            self.handleError(record)


def setup(
    level: int | str = logging.INFO,
    stream: object | None = None,
    path: Path | None = None,
) -> None:
    """Attach the project's handlers to the ``kohakuefda`` logger; safe to call twice.

    ``level`` accepts a name or a number, ``stream`` defaults to stderr, and ``path`` adds an
    uncoloured file handler beside it.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger(ROOT)
    for handler in _handlers:
        root.removeHandler(handler)
        handler.close()
    _handlers.clear()
    target = stream if stream is not None else sys.stderr
    console = FlushingHandler(target)
    console.setFormatter(Formatter(supports_colour(target)))
    _handlers.append(console)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = logging.FileHandler(path, encoding="utf-8")
        record.setFormatter(Formatter(False))
        _handlers.append(record)
    for handler in _handlers:
        handler.setLevel(level)
        root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


def set_level(level: int | str) -> None:
    """Raise or lower what the project logs, handlers included."""
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger(ROOT).setLevel(level)
    for handler in _handlers:
        handler.setLevel(level)


def get_logger(name: str) -> EfdaLogger:
    """The logger for a module, of the class that takes structured fields."""
    logger = logging.getLogger(name)
    if not isinstance(logger, EfdaLogger):
        logger.__class__ = EfdaLogger
    return logger
