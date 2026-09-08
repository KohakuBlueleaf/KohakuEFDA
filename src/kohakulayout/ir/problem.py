"""The Problem: a netlist bound to a fabric and a physics id. The engine's unit of work."""

from typing import Any, ClassVar

from kohakulayout.ir.base import Level, jsonable
from kohakulayout.ir.fabric import Fabric
from kohakulayout.ir.netlist import Netlist


class Problem(Level):
    level: ClassVar[str] = "problem"
    physics: str = ""
    fabric: Fabric
    netlist: Netlist
    params: dict[str, Any] = {}

    def check(self) -> list[str]:
        problems = self.fabric.check() + self.netlist.check()
        if (
            self.physics
            and self.netlist.pack
            and self.physics.split("@")[0] != self.netlist.pack.split("@")[0]
        ):
            problems.append(
                f"problem: physics {self.physics!r} and netlist pack {self.netlist.pack!r} differ"
            )
        flat = self.netlist.flatten()
        for fp in self.netlist.library.values():
            if fp.layer not in self.fabric.layers:
                problems.append(
                    f"footprint {fp.id}: layer {fp.layer!r} is not a fabric layer"
                )
            for layer in fp.occludes:
                if layer not in self.fabric.layers:
                    problems.append(
                        f"footprint {fp.id}: occludes unknown layer {layer!r}"
                    )
            for port in fp.ports:
                if port.carrier not in self.fabric.carriers:
                    problems.append(
                        f"footprint {fp.id}: port {port.id} carrier {port.carrier!r} is not in the fabric"
                    )
        for net in flat.nets.values():
            carrier = self.fabric.carriers.get(net.carrier)
            if carrier is None:
                problems.append(
                    f"net {net.id}: carrier {net.carrier!r} is not in the fabric"
                )
            elif carrier.capacity is not None and net.rate > carrier.capacity:
                problems.append(
                    f"net {net.id}: rate {net.rate} exceeds the capacity of {net.carrier}"
                )
            if net.outside is not None and net.outside not in self.fabric.entries:
                problems.append(
                    f"net {net.id}: enters from {net.outside}, which is not an entry side"
                )
        return problems

    def canonical(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "schema_version": self.schema_version,
            "physics": self.physics,
            "fabric": jsonable(self.fabric.model_dump(mode="python")),
            "netlist": jsonable(self.netlist.flatten().model_dump(mode="python")),
            "params": jsonable(self.params),
        }
