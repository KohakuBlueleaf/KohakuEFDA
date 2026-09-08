"""Legalisation: a floorplan becomes a real layout through the builder, channels reserved while it is placed."""

from typing import Any

from kohakulayout.ir import Assessment, Refusal


def clear(builder: Any) -> None:
    for cell_id in list(builder.placements):
        builder.withdraw(cell_id)
    for tag in list(builder.world.reservations):
        builder.release(tag)
    builder.world.forget_routes()


def pinned(builder: Any) -> Any:
    """Every cell the representation left out (the pack pins it) at its first open anchor."""
    for cell_id in builder.unplaced():
        anchor = builder.first_open(cell_id)
        if anchor is None:
            return Refusal(
                stage="region",
                subject=f"cell:{cell_id}",
                detail="no open anchor for it",
            )
        refusal = builder.place(cell_id, anchor)
        if refusal is not None:
            return refusal
    return None


def legalize(representation: Any, structure: Any, ctx: Any) -> Assessment | None:
    """Decode the structure with its channels reserved; the assessment when every cell lands, else None."""
    token = ctx.snapshot()
    channels = representation.channels(structure, ctx)

    def body(builder: Any) -> Any:
        clear(builder)
        for tag, layer, cells, carrier in channels:
            builder.reserve(tag, layer, cells, carrier)
        refusal = representation.decode(structure, builder)
        if refusal is None:
            refusal = pinned(builder)
        for tag, _, _, _ in channels:
            builder.release(tag)
        return refusal

    result = ctx.attempt(body, label="legalize")
    if result.refusal is not None:
        ctx.restore(token)
        return None
    world = ctx.world
    if len(world.placements) != len(world.netlist.cells):
        ctx.restore(token)
        return None
    assessment = ctx.consider()
    if assessment is None:
        ctx.restore(token)
    return assessment


__all__ = ["clear", "legalize", "pinned"]
