"""Parity tests need the native twin; they skip cleanly when it is not built."""

import pytest

pytest.importorskip("kohakulayout_rs")
