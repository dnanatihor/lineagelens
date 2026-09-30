# LineageLens — Column-level SQL lineage, impact analysis, interactive viewer, and agent

[![CI](https://github.com/ovaledge/lineagelens/actions/workflows/ci.yml/badge.svg)](https://github.com/ovaledge/lineagelens/actions/workflows/ci.yml)

> **Status:** under construction. The design and build plan are in [SPEC.md](SPEC.md).

## Why

Warehouse teams need to know which columns change value, and which statements stop compiling, when an upstream column changes or disappears. Single-statement lineage parsers stop at one query, so cross-file impact is still traced by hand. LineageLens builds a project-wide column graph with typed direct and indirect edges so those two questions stay distinct and every claim can point at a file and line.

## Quickstart

Planned for Phase 6. The package installs a `lineagelens` command (`build`, `impact`, `export`, `serve`, `ask`). Those commands accept the arguments in [SPEC.md](SPEC.md) §7 and report that the behaviour is not implemented yet.

## Licence

Apache-2.0
