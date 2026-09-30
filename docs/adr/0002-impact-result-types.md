# 0002 — Impact result types

- Status: accepted
- Date: 2026-09-30

## Context

SPEC.md §4 lists `ImpactResult` among the core models. §6 defines two functions with different semantics, `impact_of_change` returning `ChangeImpact` and `impact_of_drop` returning `DropImpact`. The project rules forbid merging those semantics.

## Options considered

1. One `ImpactResult` model with optional fields for both questions — hides the distinction §6 requires.
2. Two frozen models, `ChangeImpact` and `DropImpact`, with `ImpactResult` as their union — matches both names in the spec.

## Decision

`ChangeImpact` holds `direct`, `indirect`, and `evidence`. `DropImpact` holds `failing_statements`, `broken_tables`, `affected_columns`, and `evidence`. `ImpactResult` is the union of those two models. `expected_impact.json` records the column sets and statement ids named in §9.1. Evidence edges are part of the model and default to empty in that fixture until Phase 3 can attach the edges the implementation actually produces.

## Consequences

Callers must branch on the result type. Phase 3 compares the fixture's change and drop fields and is free to populate `evidence` without rewriting those fields.
