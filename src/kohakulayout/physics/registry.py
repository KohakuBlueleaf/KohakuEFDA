"""Pack discovery: explicit registration, then entry points. An unknown pack is named, not crashed on."""

from importlib import import_module
from importlib.metadata import entry_points
from typing import Any

from kohakulayout.errors import PhysicsError

ENTRY_POINT_GROUP = "kohakulayout.physics"
_PACKS: dict[str, type] = {}


def register(pack: type) -> type:
    """Register a physics class under its ``id``. Usable as a decorator."""
    _PACKS[pack.id] = pack
    return pack


def discover() -> None:
    """Load every pack advertised through the ``kohakulayout.physics`` entry-point group."""
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        pack = entry.load()
        _PACKS.setdefault(getattr(pack, "id", entry.name), pack)


def known() -> tuple[str, ...]:
    return tuple(sorted(_PACKS))


def locate(path: str) -> Any:
    """The physics class at ``module:qualname``; a worker process rebuilds a pack from this."""
    module_name, _, qualname = path.partition(":")
    target: Any = import_module(module_name)
    for part in qualname.split("."):
        target = getattr(target, part)
    return target


def path_of(physics: Any) -> str:
    cls = physics if isinstance(physics, type) else type(physics)
    return f"{cls.__module__}:{cls.__qualname__}"


def get(ref: str, **kwargs: Any) -> Any:
    """An instance of the pack ``id`` or ``id@version``; raises :class:`PhysicsError` naming what is known."""
    name = ref.split("@", 1)[0]
    pack = _PACKS.get(name)
    if pack is None:
        discover()
        pack = _PACKS.get(name)
    if pack is None:
        raise PhysicsError(f"no physics pack {name!r}; known: {list(known())}")
    return pack(**kwargs)
