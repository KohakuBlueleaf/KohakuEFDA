---
title: The IR and its text form
summary: The levels a netlist passes through on its way to a layout, the hierarchy they may carry, the `.kl` line language beside canonical JSON, and the digest both forms share.
tags:
  - kohakulayout
  - ir
---

# The IR and its text form

Every stage of the framework reads one level and writes the next. Each level is a pydantic
model with `extra="forbid"`, a `check()` that lists structural problems, a canonical JSON
form, a text form, and a digest.

| level | class | holds |
|---|---|---|
| L3 | `Netlist` | a footprint library, cells with pins and constraints, nets with sources and sinks, groups, and optionally modules and macros |
| — | `Problem` | a physics id, a `Fabric` (grid size, layers, carriers, regions, entries), a netlist and parameters |
| L2 | `Layout` | placements (cell, x, y, rotation), instances of macros, wires as segments of cells per layer, units, reservations |
| L1 | `Assessment` | the framework metrics, the pack's terms, findings, `complete` and `valid` |
| — | `Refusal`, `Frame` | why an attempt was refused (a stage from the chain); a snapshot of a run for a viewer |

Rates are `fractions.Fraction`, written as `n/d` in text and JSON; floats never enter the IR.
Coordinates run x to the right and y down; a footprint is anchored at its top-left cell and
rotates clockwise in steps of ninety degrees about that anchor. A pin's *attach cell* is the
outward neighbour of its port: where a wire meets the cell.

## Hierarchy: modules and macros

A module is a netlist with ports bound to inner pins. A macro is a module with a layout
fragment; its footprint is derived from the fragment, with each port at the attach cell of
its inner pin on the macro's edge. An instance is a cell that names a module or a macro.
Hierarchy is supported, never enforced: `Netlist.flatten()` expands every instance (ids
joined with `/`, port nets merged) and the digest is always taken on the flat form, so a
process that only wants leaves loses nothing.

## The `.kl` text form

One statement per line, braces for blocks, `;` or newlines between block items, `#`
comments. A file may hold any combination of a problem, a netlist, a layout and an
assessment; later files see earlier ones as context.

```
kl 1
physics gates@1
fabric 24x12 layers=ground,overhead entries=W,E
carrier wire ground
carrier clk overhead
lib AND 3x3 { a in wire W0 ; b in wire W2 ; y out wire E1 }
lib IN  1x1 { y out wire E0 }
lib OUT 1x1 { a in wire W0 }
cell a  IN  at=edge side=W
cell b  IN  at=edge side=W
cell g1 AND +endfield.zone=2
cell y  OUT at=edge side=E
net n1 wire : a.y -> g1.a
net n2 wire : b.y -> g1.b
net n3 wire 30 : g1.y -> y.a

layout
place a  0,2 r0
place g1 6,2 r0
wire n1 : a.y E4 -> g1.a
```

`at=<kind>` names a cell's constraint kind; any other `key=value` on a cell is a constraint
attribute under the pack's namespace; `+ns.key=value` is an attribute. A wire is written as
moves (`E4 S2`) between pin endpoints when the problem is in context, or as explicit cells
with `carrier=` and `layer=` when it is not. The grammar is `ir/text/kl.lark`; the writer
produces one canonical text per level (sorted ids, fixed option order), so a text round trip
is byte for byte.

## JSON, digests and the dev commands

`to_json()` writes canonical JSON (sorted keys, no whitespace) with the hierarchy kept;
`digest()` hashes the flat canonical form, so a hierarchical netlist and its flattening share
one digest. The `kl` command line covers `verify`, `json`, `text`, `pretty` (an ASCII grid),
`flatten`, `diff`, `route`, `assess`, `solve` and `runs`; every one takes `.kl` or `.json`
files and writes the same two forms.
