"""FactoryItemTable + ItemTable → ``Item`` records, with filled containers named by their
contents (the game names every "Cuprium Bottle" alike; the dataset keeps one item per content).
"""

from kohakuefda.data.normalize.tables import RawTables, as_int, names_of
from kohakuefda.model.items import Item, Phase
from kohakuefda.model.names import Names
from kohakuefda.model.recipes import Recipe


def build_items(tables: RawTables) -> dict[str, Item]:
    factory_items = tables["FactoryItemTable"]
    item_table = tables["ItemTable"]
    items: dict[str, Item] = {}
    for item_id, record in factory_items.items():
        en, cn = names_of(item_table.get(item_id, {}))
        limit = as_int(record.get("buildingBufferStackLimit"), -1)
        items[item_id] = Item(
            id=item_id,
            names=Names(en=en or item_id, zh_cn=cn),
            phase=Phase(as_int(record.get("phaseType"), 1)),
            buffer_limit=None if limit < 0 else limit,
            value=as_int(record.get("value")),
            storable=bool(record.get("showInUnloader", False)),
        )
    return items


def _contents(
    item_id: str, makers: dict[str, list[Recipe]], items: dict[str, Item]
) -> str | None:
    """The fluid a filling recipe (empty container of the same name in, one fluid in) puts into ``item_id``."""
    name = items[item_id].names.en
    for recipe in makers.get(item_id, []):
        fluids = [
            s.item_id
            for s in recipe.inputs
            if items[s.item_id].phase is not Phase.SOLID
        ]
        container = any(
            s.item_id != item_id and items[s.item_id].names.en == name
            for s in recipe.inputs
        )
        if container and len(fluids) == 1:
            return fluids[0]
    return None


def _with_contents(name: str, contents: str, wide: bool) -> str:
    if not name:
        return ""
    return f"{name}（{contents}）" if wide else f"{name} ({contents})"


def name_contents(
    items: dict[str, Item], recipes: dict[str, Recipe]
) -> dict[str, Item]:
    """Items that share a display name and are filled by a recipe get the fluid's name appended."""
    by_name: dict[str, list[str]] = {}
    for item in items.values():
        by_name.setdefault(item.names.en, []).append(item.id)
    makers: dict[str, list[Recipe]] = {}
    for recipe in recipes.values():
        for stack in recipe.outputs:
            makers.setdefault(stack.item_id, []).append(recipe)
    for ids in by_name.values():
        if len(ids) < 2:
            continue
        for item_id in ids:
            contents = _contents(item_id, makers, items)
            if contents is None:
                continue
            item = items[item_id]
            fluid = items[contents].names
            item.names = Names(
                en=_with_contents(item.names.en, fluid.en, False),
                zh_tw=_with_contents(item.names.zh_tw, fluid.get("zh-TW"), True),
                zh_cn=_with_contents(item.names.zh_cn, fluid.get("zh-CN"), True),
            )
    return items
