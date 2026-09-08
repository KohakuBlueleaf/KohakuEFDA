#!/usr/bin/env python3
"""Stop hook: the KohakuTPU round-end discipline for the KohakuLayout work.

Reads the hook JSON on stdin, finds the last assistant text block in the transcript and,
when that block does not end the round properly, blocks the stop once with the three
obligations: recall the plan and rules, record progress, reconcile divergences. A round is
properly ended when the block carries the goal checklist and the first-principle line.
`stop_hook_active` and a SHA guard keep it from firing twice on the same block.
"""

import hashlib
import json
import sys
from pathlib import Path

GOAL_HEADER = "## Kohaku Second Principle"
FIRST_PRINCIPLE = "following kohaku first principle"
STATE = Path(__file__).resolve().parent / ".state" / "round_end.sha"
PLAN = ".internal/kohakulayout/12-impl-plan.md"
PROGRESS = ".internal/kohakulayout/progress/status.md and rounds.md"

REASON = (
    "Round end (KohakuTPU loop). Before stopping, do the three things, then end your "
    "final text block with the goal block and the first-principle line:\n"
    f"1. RECALL: re-read {PLAN} (the milestone table, the gate you are at) and the rules "
    "in CLAUDE.md `## KohakuLayout`; name the milestone and gate you are on.\n"
    f"2. RECORD: update {PROGRESS} with what was built this round, which gate ran and "
    "its result, what was measured, and what is next.\n"
    "3. RECONCILE: list every divergence from the design set or violation of a rule "
    "(file cap, nesting, isolation, imports, comment budget, no game names in the "
    "framework) and either fix it now or record it as an open item with a reason.\n"
    "A bad gate starts a new loop for that milestone, never a patch.\n"
    f"Then append:\n{GOAL_HEADER} — Goal\n- [x]/[ ] M0 … M12 with the current state\n"
    f"{FIRST_PRINCIPLE}"
)


def last_assistant_text(transcript: Path) -> str:
    """The concatenated text blocks of the last assistant message in the transcript."""
    text = ""
    with transcript.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            content = (entry.get("message") or {}).get("content") or []
            blocks = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if blocks:
                text = "\n".join(blocks)
    return text


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    transcript = Path(payload.get("transcript_path", ""))
    if not transcript.is_file():
        return 0
    text = last_assistant_text(transcript)
    if GOAL_HEADER in text and FIRST_PRINCIPLE in text:
        return 0
    sha = hashlib.sha1(text.encode("utf-8")).hexdigest()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    if STATE.is_file() and STATE.read_text() == sha:
        return 0
    STATE.write_text(sha)
    print(json.dumps({"decision": "block", "reason": REASON}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
