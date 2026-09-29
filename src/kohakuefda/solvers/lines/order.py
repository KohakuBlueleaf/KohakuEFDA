"""The order of the items along each lines row: under their partners' ports, loops together, guests at the ends."""

from typing import Any

Box = tuple[int, int, int, int]


class LineOrder:
    """The ordering half of ``LineGraph``; mixed into it."""

    bricks: list[str]
    links: dict[str, list[tuple]]
    feeds: dict[str, list[tuple]]

    def reorder(
        self, rows: list[list[str]], boxes: dict[str, Box], rot: dict[str, int]
    ) -> bool:
        """Each row sorted by the x that lines its items up with their partners' ports,
        from the deepest row up, then from the bus down; an item with partners along
        its own row only at their mean; a loop's members together (a pipe band from the
        middle out); guests at the row's end nearest their partners; the bus-fed belt
        items kept in one run. Whether any row changed."""
        changed = False
        row_of = {i: k for k, row in enumerate(rows) for i in row}
        xs = {i: box[0] for i, box in boxes.items()}

        def centre(item: str) -> float:
            x, _, w, _ = boxes[item]
            return x + w / 2

        def key_of(item: str, k: int, row: list[str], deeper: bool) -> float:
            found = [
                link
                for link in [*self.links[item], *self.feeds[item]]
                if link[0] in row_of
                and link[0] in xs
                and link[0] not in row
                and (row_of[link[0]] > k) == deeper
            ]
            own = [link for link in found if self.exclusive(item, link, set(row))]
            wants = sorted(self.aligned(item, link, xs, rot) for link in own or found)
            if wants:
                return float(wants[(len(wants) - 1) // 2])

            fed = {m for m, *_ in self.feeds[item] if m in row}
            feeding = {t for t, *_ in self.links[item] if t in row}
            beside = {m for m in fed | feeding if m in boxes}
            if not beside:
                return float(xs.get(item, 0))
            key = sum(centre(m) for m in beside) / len(beside)
            return key + 0.5 * (len(fed - feeding) - len(feeding - fed))

        def sweep(sequence: list[int], deeper: bool) -> None:
            nonlocal changed
            for k in sequence:
                row = rows[k]
                pos = {i: n for n, i in enumerate(row)}
                own = {i: key_of(i, k, row, deeper) for i in row}
                keys: dict[str, tuple] = {}
                for item in row:
                    loop = [i for i in self.loop_of(item) if i in row]
                    if len(loop) > 1:
                        mean = sum(own[i] for i in loop) / len(loop)
                        inner = (
                            self.mirrored(loop) if self.piped(item) else sorted(loop)
                        )
                        keys[item] = (mean, inner.index(item), 0)
                    else:
                        keys[item] = (own[item], own[item], pos[item])
                self.ends(row, keys, rot)

                ordered = sorted(row, key=keys.get)
                fed = [
                    i
                    for i in ordered
                    if any(m in self.bricks for m, *_ in self.feeds[i])
                    and not self.piped(i)
                ]
                if fed:
                    lo, hi = ordered.index(fed[0]), ordered.index(fed[-1])
                    if any(i not in fed for i in ordered[lo:hi]):
                        loose = [(n, i) for n, i in enumerate(ordered) if i not in fed]
                        before = [i for n, i in loose if n - lo <= hi - n]
                        after = [i for n, i in loose if n - lo > hi - n]
                        ordered = [*before, *fed, *after]
                if ordered != row:
                    changed = True
                    row[:] = ordered

        sweep(list(range(len(rows) - 1, -1, -1)), True)
        sweep(list(range(len(rows))), False)
        return changed

    def ends(self, row: list[str], keys: dict[str, tuple], rot: dict[str, int]) -> None:
        """The row's guests moved to the end nearest their partners, a loop they belong with right beside them."""
        guests = self.guests(row, rot)
        if not guests:
            return

        hosts = [i for i in row if i not in guests and rot.get(i, 0) == 0]
        middle = sum(keys[i][0] for i in hosts) / len(hosts)
        for i in guests:
            far = -1e9 if keys[i][0] <= middle else 1e9
            keys[i] = (far, *keys[i][1:])
            mates = {t for t, *_ in self.links[i]} | {m for m, *_ in self.feeds[i]}
            for j in row:
                if j in mates and len(self.loop_of(j)) > 1:
                    near = far + (1 if far < 0 else -1)
                    for member in self.loop_of(j):
                        if member in row:
                            keys[member] = (near, *keys[member][1:])

    def guests(self, row: list[str], rot: dict[str, int]) -> list[str]:
        """The row's turned items outside any loop, when the items facing the bus are more than half the row."""
        guests = [i for i in row if rot.get(i, 0) == 180 and len(self.loop_of(i)) == 1]
        hosts = [i for i in row if i not in guests and rot.get(i, 0) == 0]
        return guests if guests and len(hosts) > len(row) / 2 else []

    def loop_of(self, item: str) -> list[str]: ...

    def mirrored(self, loop: list[str]) -> list[str]: ...

    def piped(self, item: str) -> bool: ...

    def exclusive(self, item: str, link: Any, row: set[str]) -> bool: ...

    def aligned(
        self, item: str, link: Any, xs: dict[str, int], rot: dict[str, int]
    ) -> int: ...


__all__ = ["LineOrder"]
