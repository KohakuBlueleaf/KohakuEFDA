"""Cooperative control of long loops: an observer that receives frames and a cancellation check."""

from collections.abc import Callable

Observe = Callable[[dict], None]
Cancelled = Callable[[], bool]


class CancelledError(RuntimeError):
    """The loop stopped because its cancellation check answered true."""
