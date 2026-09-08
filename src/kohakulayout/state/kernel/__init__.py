"""Kernels: the occupancy grid behind the world, in Python and, later, in Rust."""

from kohakulayout._rust import HAS_RUST
from kohakulayout.state.kernel.native import NativeKernel
from kohakulayout.state.kernel.protocol import Holder, Kernel, holder_kind
from kohakulayout.state.kernel.python import PyKernel
from kohakulayout.state.kernel.recording import RecordingKernel, replay
from kohakulayout.state.kernel.tables import ShareTable

KERNELS: dict[str, type] = {"python": PyKernel, "native": NativeKernel}


def make_kernel(name: str, width: int, height: int, layers: tuple[str, ...]) -> Kernel:
    """The kernel registered as ``name``; ``auto`` is the native twin when it is built, else Python."""
    if name == "auto":
        name = "native" if HAS_RUST else "python"
    cls = KERNELS.get(name)
    if cls is None:
        raise KeyError(f"no kernel {name!r}; known: {sorted(KERNELS)}")
    return cls(width, height, layers)


__all__ = [
    "KERNELS",
    "Holder",
    "Kernel",
    "NativeKernel",
    "PyKernel",
    "RecordingKernel",
    "ShareTable",
    "holder_kind",
    "make_kernel",
    "replay",
]
