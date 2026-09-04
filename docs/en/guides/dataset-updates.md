---
title: Dataset updates
summary: Pin a game version, rebuild the dataset, compare two versions, and tell a blind-safe update from one that needs code.
tags:
  - guides
  - data
---

# Dataset updates

The tool never reads game tables at run time. It reads one normalised `dataset.json`, built once per game version and checked into `data/<versionId>/`. The version id is the manifest id published by AKEData, for example `1.5.3@9764758-3`: game version, `@`, hotfix.

## Fetch and rebuild

```bash
kohakuefda data fetch                          # newest published version
kohakuefda data fetch --version 1.5.3@9764758-3
kohakuefda data fetch --version 1.5.3@9764758-3 --refresh --no-wiki
```

`fetch` reads the AKEData manifest to resolve the version, downloads the factory tables (from the `555me/beyondGameData` mirror by default, because it inlines the English and Simplified Chinese names that the AKEData tables replace with hashes; `--source akedata` switches), writes a SHA-256 manifest of every raw file, verifies it, builds the dataset, fetches Traditional Chinese names from the wiki for every machine and item (`--no-wiki` skips), and rebuilds with those names attached. `--refresh` re-downloads tables that are already cached.

The build is deterministic: rebuilding the same version writes a byte-identical `dataset.json`.

## Compare versions

```bash
kohakuefda data check
kohakuefda data check --pinned 1.5.3@9764758-3
kohakuefda data diff 1.5.3@9764758-3 1.6.0@abc1234-1
```

`data check` fetches the manifest, compares the newest published version against the pinned one (the newest built by default), and classifies the difference:

- **blind-safe**: items, recipes or numbers changed inside table schemas the normaliser already understands. Fetching the new version is enough.
- **needs handler**: a new machine type, port shape, mode, logistics table, factory constant or schema field appeared. The normaliser must be extended before the new version can be trusted.

`data diff` compares two built datasets and lists added, removed and changed ids per collection.

## What ships

Only numbers, identifiers and display names ship in the dataset: no raw tables, no icons, no text beyond names. Raw downloads stay under `data/raw/`, which is ignored by git. [Dataset](../reference/dataset.md) describes the file's shape and every table it is built from.
