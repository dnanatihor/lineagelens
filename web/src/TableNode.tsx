import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type TableNodeData = {
  table: string;
  columns: string[];
  level: "column" | "table";
  selected: string | null;
  upstream: string[];
  downstream: string[];
  impact: string[];
  onSelect: (fqn: string) => void;
};

export type TableFlowNode = Node<TableNodeData, "table">;

export function TableNode({ data }: NodeProps<TableFlowNode>) {
  return (
    <div className="table-node">
      <header className="table-header">{data.table}</header>
      {data.level === "column"
        ? data.columns.map((column) => {
            const fqn = `${data.table}.${column}`;
            const tone = data.impact.includes(fqn)
              ? "impact"
              : data.selected === fqn
                ? "selected"
                : data.upstream.includes(fqn)
                  ? "upstream"
                  : data.downstream.includes(fqn)
                    ? "downstream"
                    : "";
            return (
              <div className={`column-row ${tone}`} key={column}>
                <Handle type="target" id={column} position={Position.Left} />
                <button type="button" className="column-button" onClick={() => data.onSelect(fqn)}>
                  {column}
                </button>
                <Handle type="source" id={column} position={Position.Right} />
              </div>
            );
          })
        : null}
    </div>
  );
}
