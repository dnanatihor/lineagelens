import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";

import { TableNode, type TableFlowNode } from "./TableNode";

const data: TableFlowNode["data"] = {
  table: "raw.orders",
  columns: ["id", "status"],
  level: "column",
  selected: "raw.orders.id",
  upstream: [],
  downstream: ["raw.orders.status"],
  impact: [],
  onSelect: () => undefined,
};

function renderNode(overrides: Partial<TableFlowNode["data"]> = {}) {
  const node = {
    id: "raw.orders",
    type: "table" as const,
    position: { x: 0, y: 0 },
    data: { ...data, ...overrides },
  } satisfies TableFlowNode;
  return render(
    <ReactFlowProvider>
      <TableNode {...({ id: node.id, data: node.data, type: "table" } as NodeProps<TableFlowNode>)} />
    </ReactFlowProvider>,
  );
}

test("a table node lists its columns and reports the clicked column", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  renderNode({ onSelect });
  expect(screen.getByText("raw.orders")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "status" }));
  expect(onSelect).toHaveBeenCalledWith("raw.orders.status");
});

test("upstream is blue and downstream is orange", () => {
  renderNode();
  expect(screen.getByRole("button", { name: "status" }).closest(".column-row")).toHaveClass(
    "downstream",
  );
  expect(screen.getByRole("button", { name: "id" }).closest(".column-row")).toHaveClass("selected");
});
