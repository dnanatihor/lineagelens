# LineageLens — Column-Level SQL Lineage, Impact Analysis, Viewer, and Agent

| | |
|---|---|
| Repo name | `lineagelens` |
| Version | 0.1.0 |
| Size | Medium |
| Depends on | nothing; consumed by `contract-sentinel` and the agent-first catalog |

---

## 0. Using this spec with Cursor

Save as `SPEC.md` at the repo root. Implement one phase at a time from §10 with the prompts in Appendix A. Phase 1 begins with a spike test that pins how the installed `sqlglot` version represents lineage; everything else builds on that.

If this repository was created with the portfolio bootstrap, the prompts below are already filled in per phase in `CURSOR_PROMPTS.md`, and `.cursor/rules/project.mdc` already contains the project rules from Appendix A.

---

## 1. Purpose and scope

### 1.1 What it does

LineageLens builds a **project-wide, column-level lineage graph** from SQL files or a dbt project. It classifies each edge using OpenLineage's transformation vocabulary, answers impact questions ("what breaks if I drop this column?"), exports to OpenLineage and Mermaid, and ships an interactive React Flow viewer plus a LangGraph agent that explains impact in plain language, citing file and line.

### 1.2 Prior art and differentiation

`sqlglot.lineage` traces one output column through one query. `sqllineage` and OpenLineage's SQL parser extract lineage per statement. LineageLens builds on `sqlglot` and adds: a cross-statement, cross-file graph with schema accumulation; dbt manifest ingestion; typed direct and indirect edges; table- and column-level impact analysis with distinct "drop" and "change" semantics; and the viewer and agent.

### 1.3 Goals

1. Correct lineage for common warehouse SQL (CTAS, INSERT…SELECT, CREATE VIEW, CTEs, subqueries, UNION, JOINs, aggregates, CASE, window functions).
2. Never crash on unsupported SQL: produce a partial graph plus diagnostics.
3. A clean, typed library API that other projects can depend on.

### 1.4 Non-goals

Runtime lineage (query logs), stored procedures and dynamic SQL, non-SQL transformations (Python/Spark code), and a persistent lineage server.

---

## 2. Technology stack

| Concern | Choice |
|---|---|
| Parsing | `sqlglot` (dialects: postgres, snowflake, bigquery, duckdb in v0.1) |
| Graph | `networkx` `MultiDiGraph` |
| Models / CLI | `pydantic` v2, `typer`, `rich` |
| API for viewer | `fastapi` + `uvicorn` |
| Viewer | React + TypeScript + Vite, `@xyflow/react`, `elkjs` layout |
| Agent | `langgraph`, `langchain` `init_chat_model` |
| Quality | `pytest`, `ruff`, `mypy --strict`; `vitest` for the viewer |

The built viewer is bundled into the wheel at `lineagelens/web/dist` by CI.

---

## 3. Repository layout

```
lineagelens/
├── src/lineagelens/
│   ├── models.py            # ColumnRef, Edge, Statement, Diagnostic, ImpactResult
│   ├── sources/{files.py, dbt.py}
│   ├── schema.py            # SchemaRegistry (declared + accumulated)
│   ├── extract.py           # per-statement extraction
│   ├── project.py           # ordering, graph assembly
│   ├── graph.py             # LineageGraph wrapper
│   ├── impact.py
│   ├── export/{json.py, openlineage.py, mermaid.py}
│   ├── server.py            # FastAPI for the viewer
│   ├── agent/{tools.py, graph.py, prompts/}
│   └── cli.py
├── web/                     # React viewer source
└── tests/
    ├── spike/test_sqlglot_lineage_shape.py
    └── fixtures/
        ├── warehouse/*.sql
        ├── warehouse/schema.yaml
        ├── warehouse/expected_edges.json
        ├── warehouse/expected_impact.json
        ├── statements/<case>.sql + <case>.expected.json
        └── dbt_project/target/{manifest.json, catalog.json}
```

---

## 4. Core model (`models.py`)

```python
class ColumnRef(Frozen):
    database: str | None
    schema_: str | None = Field(alias="schema")
    table: str
    column: str
    def fqn(self) -> str: ...          # normalised per dialect case rules

EdgeType = Literal["DIRECT", "INDIRECT"]
EdgeSubtype = Literal["IDENTITY", "TRANSFORMATION", "AGGREGATION",
                      "FILTER", "JOIN", "GROUP_BY", "SORT", "WINDOW", "CONDITIONAL"]

class Edge(Frozen):
    source: ColumnRef
    target: ColumnRef
    type: EdgeType
    subtype: EdgeSubtype
    expression: str                    # SQL snippet, max 200 chars
    statement_id: str
    file: str
    line: int

class Statement(Frozen):
    id: str                            # f"{file}#{index}"
    file: str
    index: int
    line: int
    kind: Literal["ctas", "insert_select", "create_view", "select", "unsupported"]
    target_table: str | None
    reads: tuple[str, ...]             # table fqns

class Diagnostic(Frozen):
    code: str                          # L001..L006
    severity: Literal["error", "warning", "info"]
    statement_id: str | None
    message: str
```

Diagnostics: L001 unparsable statement; L002 unknown table (star cannot be expanded); L003 ambiguous or unresolved column; L004 unsupported statement kind; L005 INSERT column-count mismatch; L006 cyclic table dependency.

Subtypes follow OpenLineage's column-lineage facet. v0.1 must produce IDENTITY, TRANSFORMATION, AGGREGATION, FILTER, JOIN, GROUP_BY; SORT, WINDOW, CONDITIONAL are optional.

---

## 5. Extraction

### 5.1 Sources

- **Files:** glob of `.sql` files; split into statements with `sqlglot.parse(sql, dialect=...)`. Record each statement's starting line.
- **dbt:** read `target/manifest.json` (requires `dbt compile` beforehand; document this). For each node with `resource_type == "model"`, use `compiled_code` as the SQL and the node's `relation_name` (or `database.schema.alias`) as the target. Sources and seeds become known tables. Columns come from `target/catalog.json` when present.

### 5.2 Schema registry

Seeded from `schema.yaml` (`{table_fqn: {column: type}}`) or dbt `catalog.json`. As statements are processed in dependency order, each statement's output columns are registered for its target table, so downstream statements can expand `SELECT *` and resolve columns.

### 5.3 Project ordering

Build a table-level dependency graph (statement writes target, reads sources). Process statements in topological order. A cycle produces L006 and falls back to file order for the cycle members.

### 5.4 Per-statement algorithm

1. Identify the kind and target. For INSERT with an explicit column list, map output positions to the listed columns (L005 on count mismatch).
2. Qualify the SELECT: `sqlglot.optimizer.qualify.qualify(expr, schema=registry.as_mapping(), dialect=...)`. On failure, emit L002/L003 and continue with best effort.
3. **Direct edges:** for each output column, call `sqlglot.lineage.lineage(column, sql=select, schema=..., dialect=...)` and walk the resulting node tree to leaf source columns. Classify the projection expression: a bare column → IDENTITY; containing an aggregate function → AGGREGATION; anything else → TRANSFORMATION. Output columns with no source column (e.g. `COUNT(*)`, literals) get no direct edge.
4. **Indirect edges:** collect columns referenced in `WHERE`/`HAVING`/`QUALIFY` (FILTER), `JOIN … ON` (JOIN), and `GROUP BY` (GROUP_BY). Each gets an edge to **every** output column of the statement. Disable with `indirect: false`.
5. **CTEs and subqueries** are resolved through to base tables; intermediate CTE columns never appear as graph nodes.

The spike test in Phase 1 pins the exact shape of `lineage()` nodes (leaf detection, how source tables are represented) for the installed `sqlglot` version, and step 3 is implemented against that pinned shape.

---

## 6. Graph and impact analysis

`LineageGraph` wraps a `networkx.MultiDiGraph` (nodes = column FQNs with table attributes, edges = `Edge`) plus the statement table.

```python
def upstream(col, *, types=("DIRECT", "INDIRECT"), depth=None) -> list[ColumnRef]
def downstream(col, *, types=("DIRECT", "INDIRECT"), depth=None) -> list[ColumnRef]
def explain_path(src, dst) -> list[Edge]         # shortest path, edges in order
def impact_of_change(col) -> ChangeImpact
def impact_of_drop(col) -> DropImpact
```

The two impact functions answer different questions:

- **`impact_of_change(col)`** — the column's *values* change. `direct` = columns reachable from `col` via DIRECT-only paths (their values change). `indirect` = columns reachable via any path containing at least one INDIRECT edge, minus `direct` (which rows appear, or how they group, may change).
- **`impact_of_drop(col)`** — the column no longer exists. Every statement that references `col` in any clause **fails**. `failing_statements` = those statements; `broken_tables` = their targets plus every table downstream of those targets at table level; `affected_columns` = all columns of broken tables.

Each result carries the evidence edges (file, line, expression) so the agent and UI can cite them.

---

## 7. Exports and CLI

- `export json` — own schema: statements, edges, diagnostics, version.
- `export openlineage` — one dataset per target table with the `columnLineage` facet (`inputFields` with `transformations: [{type, subtype}]`).
- `export mermaid` — table-level or column-level flowchart for READMEs.

```
lineagelens build PATH... [--dialect D] [--schema schema.yaml] [--dbt PROJECT_DIR] [--no-indirect] -o graph.json
lineagelens impact graph.json --change COL | --drop COL [--json]
lineagelens export graph.json --format json|openlineage|mermaid [--level table|column]
lineagelens serve graph.json [--port 8765]
lineagelens ask graph.json "what breaks if I drop raw.orders.status?"
```

Exit code 0 when the graph builds (diagnostics allowed), 2 on invalid input.

---

## 8. Viewer and agent

### 8.1 Viewer (`web/`)

- The FastAPI app serves the built SPA plus `GET /api/graph`, `GET /api/impact?change=…|drop=…`, and `GET /api/search?q=…`.
- Custom table node: header with the table name, one row per column, and a handle per column row. Layout with ELK layered, left-to-right.
- Interactions: click a column to highlight its upstream (blue) and downstream (orange); toggle INDIRECT edges; filter by subtype; search box; side panel showing an edge's expression and file:line; "Impact" buttons that call the API and highlight results.
- Performance target: 300 tables × 20 columns renders and pans smoothly; beyond that, collapse to table-level view by default.

### 8.2 Agent (`agent/`)

- LangGraph ReAct agent. Tools: `search_columns`, `upstream`, `downstream`, `impact_of_change`, `impact_of_drop`, `explain_path` — all deterministic wrappers over §6.
- System prompt rules: answer only from tool results; cite every claim as `file:line`; distinguish "will break" (drop), "values change" (direct), and "results may change" (indirect); say so when a column is not found rather than guessing.
- Tests use a scripted fake chat model that issues predetermined tool calls; assertions check the tools called and that citations in the final answer exist in tool output.

---

## 9. Testing

### 9.1 Warehouse golden fixture

`tests/fixtures/warehouse/01_stg_orders.sql`:

```sql
CREATE TABLE staging.stg_orders AS
SELECT
  o.id                            AS order_id,
  o.customer_id                   AS customer_id,
  CAST(o.amount AS DECIMAL(12,2)) AS amount,
  o.created_at                    AS ordered_at
FROM raw.orders AS o
WHERE o.status <> 'cancelled';
```

`tests/fixtures/warehouse/02_fct_revenue.sql`:

```sql
CREATE TABLE marts.fct_customer_revenue AS
SELECT
  c.id             AS customer_id,
  UPPER(c.country) AS country,
  SUM(s.amount)    AS total_revenue,
  COUNT(*)         AS order_count
FROM staging.stg_orders AS s
JOIN raw.customers AS c ON s.customer_id = c.id
GROUP BY c.id, UPPER(c.country);
```

`schema.yaml` declares `raw.orders(id, customer_id, amount, created_at, status)` and `raw.customers(id, country, email)`.

Expected DIRECT edges:

| Source | Target | Subtype |
|---|---|---|
| raw.orders.id | staging.stg_orders.order_id | IDENTITY |
| raw.orders.customer_id | staging.stg_orders.customer_id | IDENTITY |
| raw.orders.amount | staging.stg_orders.amount | TRANSFORMATION |
| raw.orders.created_at | staging.stg_orders.ordered_at | IDENTITY |
| raw.customers.id | marts.fct_customer_revenue.customer_id | IDENTITY |
| raw.customers.country | marts.fct_customer_revenue.country | TRANSFORMATION |
| staging.stg_orders.amount | marts.fct_customer_revenue.total_revenue | AGGREGATION |

Expected INDIRECT edges: `raw.orders.status` → each of the 4 `stg_orders` columns (FILTER); `staging.stg_orders.customer_id` and `raw.customers.id` → each of the 4 `fct_customer_revenue` columns (JOIN); `raw.customers.id` and `raw.customers.country` → each of the 4 `fct_customer_revenue` columns (GROUP_BY). `order_count` has no DIRECT edge.

Expected impact:

| Query | Expected |
|---|---|
| change `raw.orders.amount` | direct: `stg_orders.amount`, `fct_customer_revenue.total_revenue`; indirect: none |
| change `raw.orders.status` | direct: none; indirect: all 4 `stg_orders` columns and all 4 `fct_customer_revenue` columns |
| drop `raw.orders.status` | failing: `01_stg_orders.sql#0`; broken tables: `staging.stg_orders`, `marts.fct_customer_revenue` |
| drop `raw.customers.email` | failing: none; broken tables: none |

### 9.2 Statement cases

One `.sql` + `.expected.json` per case: CTE chain, nested subquery, UNION ALL, INSERT with column list, INSERT without column list, CREATE VIEW, SELECT * with known schema, SELECT * with unknown schema (expects L002), CASE expression, window function, self-join with aliases, unparsable statement (expects L001 and no crash). Run each for postgres and snowflake dialects where syntax allows.

### 9.3 Other tests

dbt ingestion from a committed minimal `manifest.json` + `catalog.json`; OpenLineage export validated against a vendored facet JSON Schema; Mermaid snapshot; API endpoint tests; agent tests with the scripted fake model; viewer component tests with `vitest`.

---

## 10. Phases and acceptance criteria

**Phase 0 — Scaffold and fixtures.** Layout, models, CLI skeleton, all fixture files and expected JSON from §9. *Accept:* tooling passes; expected files load and validate against the models. *Baseline:* the repository baseline in Appendix B.1 is in place, including a README stub with the project name, one-line value proposition, Why, and a planned Quickstart; the CI workflow's commands pass locally.

**Phase 1 — Spike and single-statement direct lineage.** Spike test pinning `lineage()` node shape; §5.4 steps 1–3 and 5. *Accept:* all DIRECT expectations in §9.2 cases pass; the spike test documents the pinned shape in comments.

**Phase 2 — Project graph and indirect edges.** §5.1 files, §5.2, §5.3, §5.4 step 4, diagnostics. *Accept:* warehouse edges match `expected_edges.json` exactly (as a set of source, target, type, subtype); an unparsable file yields L001 without aborting the build.

**Phase 3 — Impact and exports.** §6, §7 (except `serve`, `ask`). *Accept:* `expected_impact.json` matches; OpenLineage export validates; `lineagelens impact` prints evidence with file:line.

**Phase 4 — dbt.** §5.1 dbt. *Accept:* the dbt fixture builds with the expected edge set.

**Phase 5 — Viewer.** §8.1. *Accept:* `lineagelens serve` opens the viewer on the warehouse graph; highlighting and impact buttons work; a 300-table generated graph renders.

**Phase 6 — Agent.** §8.2. *Accept:* scripted-model tests pass; every citation in answers maps to a real edge. *README:* README.md satisfies Appendix B.2 and B.3; a CI job runs the Quickstart on a fresh checkout and passes; all example output comes from real runs.

---

## 11. Conventions

Python 3.11+, `mypy --strict`, `ruff`; TypeScript strict mode for the viewer. Extraction must never raise on bad SQL; it returns diagnostics. Graph output is deterministic (sorted edges) so golden tests are stable. No network in tests.

---

## 12. Open decisions

1. **Name availability** on GitHub and PyPI.
2. **Column name normalisation** for case-sensitive dialects (quoted identifiers). Default: lowercase unquoted identifiers, preserve quoted ones.
3. **Viewer scale ceiling** — whether to add server-side subgraph extraction for very large graphs in v0.2.

---

## Appendix A — Cursor prompts

<!-- bootstrap:phase-prompt -->
```
Read SPEC.md. Implement Phase N from §10 only. Satisfy every acceptance criterion for Phase N, write tests first where the spec gives expected outputs, and do not start later phases. If anything is ambiguous, list the ambiguity and stop.
```

<!-- bootstrap:review-prompt -->
```
Review the Phase N implementation against SPEC.md. For each acceptance criterion in §10, state whether it is met and which test proves it. List every divergence from the spec. Do not fix anything yet.
```

Project rules:

<!-- bootstrap:rules -->
```
- Extraction never raises on bad SQL; it records Diagnostics and continues.
- Edge subtypes use the OpenLineage vocabulary in §4 exactly.
- impact_of_drop and impact_of_change have different semantics (§6); never merge them.
- The agent may only state facts returned by its tools and must cite file:line.
```

---

## Appendix B — Repository baseline and README

### B.1 Repository baseline (Phase 0)

- `README.md` stub (items 1, 4, and a planned Quickstart from B.2), `CHANGELOG.md` (Keep a Changelog format with an `[Unreleased]` section), `LICENSE` (Apache-2.0), `.gitignore`, and `docs/adr/` with a template. The portfolio bootstrap creates these; if the repository was created by hand, create them in Phase 0.
- `pyproject.toml` managed by `uv`, with `ruff` (lint and format) and `mypy --strict` configured there.
- `.pre-commit-config.yaml` running ruff, ruff-format, and basic hygiene hooks (trailing whitespace, end of file, YAML and JSON checks). Pin hook versions to the latest releases at Phase 0.
- `.github/workflows/ci.yml` running lint, type-check, and tests with `uv` on every push and pull request, plus the `web/` build and tests where the project has a UI. Add the CI badge to the README.
- Conventional commit messages, semantic versioning, and a CHANGELOG entry for every release.

### B.2 README requirements (Phase 6)

The README is a deliverable of Phase 6. Sections, in order:

1. `# <Name> — <one-line value proposition>`
2. Badges: CI, licence, PyPI (libraries only)
3. Demo: `![demo](docs/demo.gif)` (placeholder until recorded; see B.3)
4. Why: 2–3 sentences on the problem and who has it
5. Quickstart: one command that works on a fresh machine
6. How it works: Mermaid architecture diagram and a short walkthrough
7. Results / example output: real output from the tool (see B.3)
8. Design decisions: links to `docs/adr/`
9. Roadmap: only things not yet built
10. Licence

Rules:

- Every command in the README must run. A CI job executes the Quickstart on a fresh checkout.
- All example output comes from a real run on the repository's fixtures, never written by hand.
- Keep it under about 150 lines; longer material goes in `docs/`.

### B.3 Demo and results for this project

- **Demo:** The viewer: click a column to highlight upstream and downstream, then use the impact button.
- **Results / example output:** Output of `lineagelens impact --drop raw.orders.status` on the warehouse fixture, and a Mermaid lineage diagram generated with `lineagelens export --format mermaid`.

The demo is recorded by a person, not generated. For terminal demos, Cursor may write a `docs/demo.tape` script for `vhs`, which records terminal sessions as GIFs; re-record whenever the output changes.

README prompt for Phase 6:

<!-- bootstrap:readme-prompt -->
```
Read SPEC.md, including Appendix B. Write README.md following Appendix B.2 exactly, with the demo and results content from B.3. Take the Quickstart commands from what actually works in this repository, and add a CI job that runs them on a fresh checkout. For "Results / example output", run the tool on the included fixtures and paste the real output; do not invent any output. Leave docs/demo.gif as a placeholder with a TODO. Keep it under 150 lines and move anything longer into docs/.
```
