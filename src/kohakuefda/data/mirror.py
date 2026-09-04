"""GitHub mirror of the game tables, addressed by hotfix id through its commit history."""

import logging

import httpx

from kohakuefda.data.sources import MIRROR_COMMITS_URL, MIRROR_RAW_URL

log = logging.getLogger(__name__)


def resolve_ref(client: httpx.Client, hotfix: str) -> str:
    """Commit sha whose message names the hotfix build number; ``"main"`` when none matches."""
    build = hotfix.split("-")[0]
    response = client.get(MIRROR_COMMITS_URL, params={"per_page": 100})
    if response.status_code != 200:
        log.warning("mirror commit list request failed: %d", response.status_code)
        return "main"
    for commit in response.json():
        message = commit.get("commit", {}).get("message", "")
        if message.split()[:1] == [build]:
            log.debug("resolved hotfix %s to commit %s", hotfix, commit["sha"])
            return commit["sha"]
    log.debug("no commit matches hotfix %s; using main", hotfix)
    return "main"


def table_url(ref: str, table: str) -> str:
    return MIRROR_RAW_URL.format(ref=ref, table=table)
