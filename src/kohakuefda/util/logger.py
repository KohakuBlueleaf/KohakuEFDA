"""``EfdaLogger``: a ``logging.Logger`` whose level methods take structured fields.

Kept apart from :mod:`kohakuefda.util.logging` so the level-method overrides do not crowd the
handlers and the formatter. The overrides exist so ``log.info("laid out", width=40, height=31)``
type-checks; the merge itself happens once, in :meth:`EfdaLogger._log`. Each override adds a
frame between the caller and ``Logger._log``, and ``findCaller`` only skips frames belonging to
the stdlib logging module, so both sides raise ``stacklevel`` to keep the record pointing at the
real call site.
"""

import logging
from collections.abc import Mapping
from typing import Any

LEVELS = ("debug", "info", "warning", "error", "critical")
RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
}


class EfdaLogger(logging.Logger):
    """Logger accepting extra record fields as keyword arguments."""

    def _log(
        self,
        level: int,
        msg: object,
        args: tuple[object, ...] | Mapping[str, object],
        exc_info: Any = None,
        extra: Mapping[str, Any] | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        **fields: Any,
    ) -> None:
        merged: dict[str, Any] | None = None
        if extra is not None or fields:
            merged = dict(extra) if extra else {}
            merged.update(fields)
        super()._log(level, msg, args, exc_info, merged, stack_info, stacklevel + 1)

    def debug(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._emit(logging.DEBUG, msg, args, kwargs)

    def info(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._emit(logging.INFO, msg, args, kwargs)

    def warning(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._emit(logging.WARNING, msg, args, kwargs)

    def error(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._emit(logging.ERROR, msg, args, kwargs)

    def critical(self, msg: object, *args: object, **kwargs: Any) -> None:
        self._emit(logging.CRITICAL, msg, args, kwargs)

    def exception(self, msg: object, *args: object, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self._emit(logging.ERROR, msg, args, kwargs)

    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
        self._emit(level, msg, args, kwargs)

    def _emit(
        self, level: int, msg: object, args: tuple[object, ...], kwargs: dict[str, Any]
    ) -> None:
        """Split the call's own options from the fields and hand both to the stdlib.

        The fields travel as ``extra`` rather than as keywords so a field may be called
        ``level`` or ``msg`` without colliding with a parameter, and a field whose name a
        ``LogRecord`` already owns is suffixed instead of raising mid-run.
        """
        if not self.isEnabledFor(level):
            return
        stacklevel = int(kwargs.pop("stacklevel", 1)) + 2
        exc_info = kwargs.pop("exc_info", None)
        stack_info = bool(kwargs.pop("stack_info", False))
        fields = dict(kwargs.pop("extra", None) or {})
        fields.update(kwargs)
        extra = {(f"{k}_" if k in RESERVED else k): v for k, v in fields.items()}
        super()._log(level, msg, args, exc_info, extra or None, stack_info, stacklevel)
