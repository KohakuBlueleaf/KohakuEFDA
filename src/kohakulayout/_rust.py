"""Native twin detection: ``HAS_RUST`` is true when ``kohakulayout_rs`` imports."""

try:
    import kohakulayout_rs

    HAS_RUST = True
except ImportError:
    kohakulayout_rs = None
    HAS_RUST = False

__all__ = ["HAS_RUST", "kohakulayout_rs"]
