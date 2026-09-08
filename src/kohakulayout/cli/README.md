# kohakulayout.cli

`kl`: the dev commands over IR files, so a tool the framework has never heard of can
own any level.

## Files

| file | what it is |
|---|---|
| `__init__.py` | the typer app: `verify`, `json`, `text`, `pretty`, `flatten`, `diff`, `route` (a placed layout through a registered router), `assess` (a layout against its problem), `solve` (a problem through a solver with a budget; `--root` records the run through the local service), `runs` (the runs under a root) |
| `io.py` | reading `.kl` and `.json` files into `Levels`, merging several, picking one level |

## Dependencies

- `typer`; `kohakulayout.ir`. The top of the import order.
