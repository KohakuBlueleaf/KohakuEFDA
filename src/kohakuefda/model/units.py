"""Repeat units of a plan: tiles of machines copied as one, nested, and the flows between them."""

from kohakuefda.model.base import EfdaModel


class Tile(EfdaModel):
    """A recipe use with the feeders that attach to it: ``members`` names each attached
    recipe use (or cycle) with its machines per copy of this tile; ``copies`` is how many
    times the tile is built; ``parent`` the tile it attaches to, None at the top; ``rim``
    the recipes of the top-level tile that take an input from outside it."""

    id: str
    recipes: list[str]
    per_copy: dict[str, int]
    copies: int
    members: dict[str, int] = {}
    parent: str | None = None
    rim: list[str] = []


class Flow(EfdaModel):
    """An item flowing between two top-level tiles, or to and from the world (``""``)."""

    item_id: str
    source: str
    sink: str


class Hierarchy(EfdaModel):
    """The plan's tiles, top-level first, and the flows between top-level tiles."""

    tiles: list[Tile] = []
    flows: list[Flow] = []

    @property
    def top(self) -> list[Tile]:
        return [t for t in self.tiles if t.parent is None]

    def tile(self, tile_id: str) -> Tile:
        return next(t for t in self.tiles if t.id == tile_id)

    def root(self, tile_id: str) -> str:
        tile = self.tile(tile_id)
        return tile_id if tile.parent is None else self.root(tile.parent)

    def machines(self, tile_id: str) -> int:
        """Machines in one copy of the tile, its attached tiles included."""
        tile = self.tile(tile_id)
        return sum(tile.per_copy.values()) + sum(
            count * self.machines(member) for member, count in tile.members.items()
        )


__all__ = ["Flow", "Hierarchy", "Tile"]
