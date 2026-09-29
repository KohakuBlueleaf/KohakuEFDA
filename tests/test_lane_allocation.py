"""Transport allocation preserves rational supply and demand at every endpoint."""

import random
from collections import defaultdict
from fractions import Fraction

from kohakuefda.synth.problem import assign


def test_small_sources_are_reused_after_their_first_sink_fills() -> None:
    sources = [((f"s{i}", "out"), Fraction(1)) for i in range(8)]
    sinks = [(("a", "in"), Fraction(5)), (("b", "in"), Fraction(3))]
    lanes = assign(sources, sinks)
    delivered = defaultdict(Fraction)
    for _, sink, rate in lanes:
        delivered[sink] += rate
    assert dict(delivered) == dict(sinks)
    assert sum(rate for _, _, rate in lanes) == 8


def test_rational_allocation_conserves_flow_with_skewed_marginals() -> None:
    rng = random.Random(391)
    for _ in range(400):
        sources = [
            ((f"s{i}", "out"), Fraction(rng.randrange(60), rng.randrange(1, 8)))
            for i in range(rng.randrange(1, 12))
        ]
        sinks = [
            ((f"t{i}", "in"), Fraction(rng.randrange(60), rng.randrange(1, 8)))
            for i in range(rng.randrange(1, 12))
        ]
        lanes = assign(sources, sinks)
        supplied = defaultdict(Fraction)
        delivered = defaultdict(Fraction)
        for source, sink, rate in lanes:
            assert rate > 0
            supplied[source] += rate
            delivered[sink] += rate
        assert all(supplied[key] <= rate for key, rate in sources)
        assert all(delivered[key] <= rate for key, rate in sinks)
        assert sum(supplied.values()) == min(
            sum(rate for _, rate in sources), sum(rate for _, rate in sinks)
        )
        assert lanes == assign(sources, sinks)


def test_duplicate_endpoint_entries_are_summed() -> None:
    sources = [(("s", "out"), Fraction(1, 3)), (("s", "out"), Fraction(2, 3))]
    sinks = [(("t", "in"), Fraction(1, 4)), (("t", "in"), Fraction(3, 4))]
    assert assign(sources, sinks) == [(("s", "out"), ("t", "in"), Fraction(1))]
