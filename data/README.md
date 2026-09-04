# data/

Normalised game datasets, one directory per game version:

```
data/
├── <versionId>/dataset.json    # e.g. 1.5.3@9764758-3; the pinned dataset the library uses
└── raw/<versionId>/            # downloaded tables + SHA manifest + wiki names (git-ignored)
```

Rebuild with `kohakuefda data fetch --version <versionId>`. Compare the pinned
version with the newest published one with `kohakuefda data check`, and two
built datasets with `kohakuefda data diff <old> <new>`.

The dataset contains numbers, identifiers and display names only. Game data is
the property of Hypergryph / Gryphline; tables come from community sources
(AKEData, the `555me/beyondGameData` mirror) and zh-TW names from
endfield.wiki.gg.
