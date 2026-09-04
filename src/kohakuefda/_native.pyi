"""Type stubs for the ``_native`` Rust extension module.

The module is optional: ``kohakuefda.route.pathfinder`` uses it when it has been built and falls
back to its own search when it has not. Build it with ``maturin develop --release``.
"""

AXIS_NONE: int
AXIS_H: int
AXIS_V: int
AXIS_T: int

class _State:
    """A grid's occupancy put by; Rust frees it with this object."""

class _Grid:
    """The two-layer routing grid and its A*.

    The compiled class. Callers should use ``kohakuefda.route.pathfinder.RouteGrid``, which owns
    the same state in Python for the code that reads it back and mirrors every change into here.
    """

    def __init__(
        self,
        width: int,
        height: int,
        turn_cost: float,
        bridge_cost: float,
        history_cost: float,
    ) -> None:
        """
        Parameters
        ----------
        width, height : int
            Grid size in cells.
        turn_cost : float
            Added when a path changes direction.
        bridge_cost : float
            Added when a path crosses another lane through a bridge.
        history_cost : float
            Multiplies what a cell has been charged for being contested.
        """

    def block(self, layer: int, x: int, y: int, value: bool) -> None:
        """Close a cell of a layer to every wire, or open it."""

    def own(self, layer: int, x: int, y: int, value: bool) -> None:
        """Whether a machine's own footprint covers a cell, as against the ring."""

    def extent(self) -> tuple[int, int, int, int] | None:
        """The rectangle the line needs, or None when nothing stands yet."""

    def free_square(
        self, window: tuple[int, int, int, int], size: int, taken: list[tuple[int, int]]
    ) -> tuple[int, int] | None:
        """The first free square of size in window that is not taken."""

    def used(self) -> list[tuple[int, int]]:
        """Every cell the line uses, on either layer."""

    def unit(self, layer: int, x: int, y: int, value: bool) -> None:
        """Put a logistics unit on a cell of a layer, or take it off."""

    def hold(self, layer: int, x: int, y: int, wire: int, axis: int) -> None:
        """One wire takes a cell, travelling along ``axis`` (``AXIS_H``, ``AXIS_V``, ``AXIS_T``)."""

    def release(self, layer: int, x: int, y: int, wire: int) -> None:
        """One wire lets a cell go."""

    def reserve(self, layer: int, x: int, y: int, owners: list[int]) -> None:
        """Close a cell to every wire but ``owners``; an empty list opens it."""

    def history(self, layer: int, x: int, y: int, value: float) -> None:
        """What a cell has been charged for being contested."""

    def clear(self) -> None:
        """Take every layer back to empty."""

    def save(self) -> _State:
        """Put the whole occupancy by, to come back to with :meth:."""

    def load_state(self, state: _State) -> None:
        """Come back to a saved occupancy."""

    def load(
        self,
        layer: int,
        blocked: list[tuple[int, int]],
        owned: list[tuple[int, int]],
        units: list[tuple[int, int]],
        holders: list[tuple[int, int, int, int]],
        reserved: list[tuple[int, int, list[int]]],
        history: list[tuple[int, int, float]],
    ) -> None:
        """Refill one layer in one call, for a state restored from a snapshot."""

    def astar(
        self,
        layer: int,
        wire: int,
        starts: list[tuple[int, int, int]],
        goals: list[tuple[int, int, int]],
        present_cost: float,
        share: bool,
        limit: float,
        shared: list[tuple[int, int]] | None,
    ) -> list[tuple[int, int]] | None:
        """The cheapest path from any start to any goal, or ``None``.

        Parameters
        ----------
        layer : int
            0 for the ground, 1 for the sky.
        wire : int
            The wire searching, so its own cells are not treated as another's.
        starts, goals : list of (x, y, mask)
            ``mask`` is a bitmask over north, east, south, west of the directions a path may
            leave a start by or enter a goal by; 0 for any.
        present_cost : float
            Charged for sharing a cell when ``share`` allows it at all.
        share : bool
            Whether a cell another wire holds may be taken other than as a legal crossing.
        limit : float
            What a path may cost before the search gives up.
        shared : list of (x, y), optional
            Goal cells another wire may already hold — the tree cells this one attaches to.
            ``None`` lets every goal be shared.
        """

    def holders(self, layer: int) -> list[tuple[int, int, int, int]]:
        """Every wire holding a cell of a layer, with its axis."""

    def blocked(self, layer: int) -> list[tuple[int, int]]:
        """The cells of a layer closed to every wire."""

    def units(self, layer: int) -> list[tuple[int, int]]:
        """The cells of a layer a logistics unit stands on."""
