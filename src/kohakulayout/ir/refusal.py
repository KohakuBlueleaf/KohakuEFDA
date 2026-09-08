"""Why a placement or a route did not happen, naming its stage in the diagnostic chain."""

from kohakulayout.ir.base import Attrs, Model

STAGES: tuple[str, ...] = (
    "overlap",
    "region",
    "port_shut",
    "route",
    "unrouted",
    "field",
    "legal",
)


class Refusal(Model):
    stage: str
    subject: str = ""
    detail: str = ""
    attrs: Attrs = {}

    def __str__(self) -> str:
        return f"{self.stage}: {self.subject}: {self.detail}".rstrip(": ")
