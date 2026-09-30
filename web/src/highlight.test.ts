import { highlightColumn, visibleEdges } from "./highlight";
import type { GraphEdge } from "./types";

const edges: GraphEdge[] = [
  {
    source_table: "raw.orders",
    source_column: "status",
    target_table: "staging.stg_orders",
    target_column: "amount",
    source: "raw.orders.status",
    target: "staging.stg_orders.amount",
    type: "INDIRECT",
    subtype: "FILTER",
    expression: "status <> 'cancelled'",
    file: "01_stg_orders.sql",
    line: 1,
    statement_id: "01_stg_orders.sql#0",
  },
];

test("highlighting walks downstream of the selected column", () => {
  const highlight = highlightColumn("raw.orders.status", edges);
  expect([...highlight.downstream]).toEqual(["staging.stg_orders.amount"]);
  expect([...highlight.upstream]).toEqual([]);
});

test("the indirect toggle hides filter edges", () => {
  expect(visibleEdges(edges, false, new Set(["FILTER"]))).toEqual([]);
  expect(visibleEdges(edges, true, new Set(["IDENTITY"]))).toEqual([]);
});
