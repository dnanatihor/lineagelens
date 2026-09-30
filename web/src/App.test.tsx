import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import type { Edge, NodeProps, NodeTypes, ReactFlowProps } from "@xyflow/react";

import { App } from "./App";
import type { TableFlowNode } from "./TableNode";
import type { GraphPayload } from "./types";

vi.mock("./layout", () => ({
  layoutTables: async (tables: { name: string }[]) =>
    tables.map((table, index) => ({
      name: table.name,
      x: index * 280,
      y: 0,
      width: 240,
      height: 80,
    })),
}));

vi.mock("@xyflow/react", () => ({
  Background: () => null,
  Controls: () => null,
  ReactFlowProvider: ({ children }: { children: ReactElement }) => children,
  Handle: () => null,
  Position: { Left: "left", Right: "right" },
  ReactFlow: ({ nodes, edges, nodeTypes, onEdgeClick }: ReactFlowProps) => {
    const types = nodeTypes as NodeTypes;
    const Node = types.table as (props: NodeProps<TableFlowNode>) => ReactElement;
    return (
      <div>
        {(nodes ?? []).map((node) => (
          <Node
            key={node.id}
            {...({
              id: node.id,
              data: node.data,
              type: "table",
            } as NodeProps<TableFlowNode>)}
          />
        ))}
        {(edges ?? []).map((edge: Edge) => (
          <button key={edge.id} type="button" onClick={(event) => onEdgeClick?.(event, edge)}>
            edge {String(edge.label)}
          </button>
        ))}
      </div>
    );
  },
}));

const graph: GraphPayload = {
  view: "column",
  tables: [
    { name: "raw.orders", columns: ["status"] },
    { name: "staging.stg_orders", columns: ["amount"] },
  ],
  edges: [
    {
      source_table: "raw.orders",
      source_column: "status",
      target_table: "staging.stg_orders",
      target_column: "amount",
      source: "raw.orders.status",
      target: "staging.stg_orders.amount",
      type: "INDIRECT",
      subtype: "FILTER",
      expression: "o.status <> 'cancelled'",
      file: "01_stg_orders.sql",
      line: 1,
      statement_id: "01_stg_orders.sql#0",
    },
  ],
};

test("highlighting and impact buttons follow the warehouse graph", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/graph")) {
        return new Response(JSON.stringify(graph), { status: 200 });
      }
      if (url.startsWith("/api/impact?drop=")) {
        return new Response(
          JSON.stringify({
            kind: "drop",
            column: "raw.orders.status",
            failing_statements: ["01_stg_orders.sql#0"],
            broken_tables: ["staging.stg_orders"],
            affected_columns: ["staging.stg_orders.amount"],
            evidence: graph.edges,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    }),
  );
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "status" }));
  expect(screen.getByRole("button", { name: "amount" }).closest(".column-row")).toHaveClass(
    "downstream",
  );
  await user.click(screen.getByRole("button", { name: "edge FILTER" }));
  expect(screen.getByLabelText("Edge details")).toHaveTextContent("01_stg_orders.sql:1");
  expect(screen.getByLabelText("Edge details")).toHaveTextContent("o.status <> 'cancelled'");
  await user.click(screen.getByRole("button", { name: "Impact of drop" }));
  await waitFor(() => {
    expect(screen.getByRole("button", { name: "amount" }).closest(".column-row")).toHaveClass(
      "impact",
    );
  });
});
