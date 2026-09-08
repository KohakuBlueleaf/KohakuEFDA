#!/usr/bin/env python3
"""PostCompact hook: after a compaction, point the next turn back at the plan and the progress record."""

import json

CONTEXT = (
    "Context was compacted. Before continuing the KohakuLayout work, re-read "
    ".internal/kohakulayout/README.md, .internal/kohakulayout/12-impl-plan.md and "
    ".internal/kohakulayout/progress/status.md, then the design page of the milestone you are on. "
    "The rules are in CLAUDE.md under `## KohakuLayout`."
)

print(
    json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostCompact",
                "additionalContext": CONTEXT,
            }
        }
    )
)
