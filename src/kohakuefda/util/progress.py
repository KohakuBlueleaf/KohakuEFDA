"""Progress that never goes quiet.

A phase that says nothing for a minute is indistinguishable from a phase that has hung, so
every loop long enough to outlast a breath carries a ``Ticker``: it prints on the same line at
a fixed rate, and it prints whether or not anything improved. ``SILENCE`` is the longest a
phase may say nothing; a loop whose steps are slower than that reports from inside the step.

Writing to the stream directly, rather than through ``logging``, is what keeps the line
rewriting itself instead of scrolling. Nothing is written when the stream is not a terminal, so
a served run and a piped run keep their logs clean.
"""

import shutil
import sys
import time

EVERY = 0.2
SILENCE = 10.0
BAR = 24


class Ticker:
    """Rewrites one line with how far a phase has got."""

    def __init__(self, total: int, label: str = "", stream=None) -> None:
        self.total = max(0, total)
        self.label = label
        self.stream = stream if stream is not None else sys.stderr
        self.live = bool(getattr(self.stream, "isatty", lambda: False)())
        self.started = time.monotonic()
        self.last = 0.0
        self.width = 0

    def tick(self, done: int, what: str = "", failed: int = 0) -> None:
        """Show progress, at most every ``EVERY`` seconds."""
        now = time.monotonic()
        if now - self.last < EVERY and done < self.total:
            return
        self.last = now
        self.draw(self.line(done, what, failed))

    def line(self, done: int, what: str, failed: int) -> str:
        share = done / self.total if self.total else 1.0
        full = int(BAR * min(1.0, share))
        bar = "#" * full + "-" * (BAR - full)
        out = f"{self.label} [{bar}] {done}/{self.total}"
        if failed:
            out += f" {failed} unplaced"
        if what:
            out += f"  {what}"
        return f"{out}  {now_since(self.started)}"

    def draw(self, text: str) -> None:
        if not self.live:
            return
        room = shutil.get_terminal_size((100, 24)).columns - 1
        text = text[:room]
        self.stream.write("\r" + text.ljust(self.width))
        self.stream.flush()
        self.width = max(len(text), 0)

    def done(self, text: str = "") -> None:
        """Finish the line so the next log record starts on its own."""
        if not self.live:
            return
        if text:
            self.draw(text)
        self.stream.write("\n")
        self.stream.flush()
        self.width = 0


def now_since(started: float) -> str:
    seconds = time.monotonic() - started
    return f"{seconds:5.1f}s"
