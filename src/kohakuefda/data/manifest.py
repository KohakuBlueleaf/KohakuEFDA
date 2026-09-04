"""AKEData manifest: the list of published game versions."""

import logging

import httpx

from kohakuefda.data.sources import AKEDATA_MANIFEST_URL, USER_AGENT
from kohakuefda.model.base import EfdaModel

log = logging.getLogger(__name__)


class ManifestVersion(EfdaModel):
    id: str
    gameVersion: str
    hotfixVersion: str
    tableCfgPath: str
    publishedAt: str = ""


class Manifest(EfdaModel):
    schemaVersion: int
    latest: str
    versions: list[ManifestVersion]
    updatedAt: str = ""
    sharedRevision: str = ""

    def get(self, version_id: str) -> ManifestVersion:
        """The entry for ``version_id``; ``"latest"`` resolves to the newest one."""
        wanted = self.latest if version_id == "latest" else version_id
        for version in self.versions:
            if version.id == wanted:
                return version
        raise KeyError(f"version {wanted!r} is not in the AKEData manifest")


def make_client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True
    )


def fetch_manifest(client: httpx.Client) -> Manifest:
    response = client.get(AKEDATA_MANIFEST_URL)
    response.raise_for_status()
    manifest = Manifest.model_validate(response.json())
    log.debug(
        "manifest: latest %s, %d version(s)", manifest.latest, len(manifest.versions)
    )
    return manifest
