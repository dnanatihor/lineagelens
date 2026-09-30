# 0001 — Column fully qualified names

- Status: accepted
- Date: 2026-09-30

## Context

SPEC.md §4 requires `ColumnRef.fqn()` to normalise names per dialect case rules. §12 leaves quoted-identifier case as an open decision and states a default: lowercase unquoted identifiers, preserve quoted ones. Fixture column names in §9 are unquoted `schema.table.column` strings.

## Options considered

1. Lowercase every identifier, including quoted ones — simple, and wrong for quoted case-sensitive names.
2. Lowercase unquoted identifiers and preserve quoted `"`, `` ` ``, and `[]` identifiers — the default in §12.

## Decision

`ColumnRef.fqn()` joins the non-null database, schema, table, and column parts with `.`, lowercasing each unquoted part and leaving quoted parts unchanged. Warehouse and statement fixtures use unquoted lowercase parts, so a column such as `raw.orders.amount` is `schema=raw`, `table=orders`, `column=amount`.

## Consequences

Extraction must store quoted identifiers with their quotes (or an equivalent mark) so `fqn()` does not lowercase them. Dialects that fold unquoted names to uppercase are not modelled separately in v0.1; the stored form is already the normalised lowercase form.
