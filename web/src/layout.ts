import type { GraphEdge, TablePayload } from "./types";

type ElkNode = {
  id: string;
  width?: number;
  height?: number;
  x?: number;
  y?: number;
};

type ElkGraph = {
  id: string;
  layoutOptions: Record<string, string>;
  children: ElkNode[];
  edges: { id: string; sources: string[]; targets: string[] }[];
};

type ElkLayout = {
  layout: (graph: ElkGraph) => Promise<ElkGraph>;
};

export type PlacedTable = {
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

export async function layoutTables(
  tables: TablePayload[],
  edges: GraphEdge[],
  view: "column" | "table",
): Promise<PlacedTable[]> {
  const elkModule = (await import("elkjs/lib/elk.bundled.js")) as unknown as {
    default: new () => ElkLayout;
  };
  const elk = new elkModule.default();
  const sizes = new Map(
    tables.map((table) => {
      const height = view === "column" ? 40 + table.columns.length * 28 : 48;
      return [table.name, { width: 240, height }] as const;
    }),
  );
  const seen = new Set<string>();
  const elkEdges: ElkGraph["edges"] = [];
  for (const edge of edges) {
    const key = `${edge.source_table}->${edge.target_table}`;
    if (seen.has(key) || edge.source_table === edge.target_table) {
      continue;
    }
    seen.add(key);
    elkEdges.push({
      id: key,
      sources: [edge.source_table],
      targets: [edge.target_table],
    });
  }
  const laid = await elk.layout({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.spacing.nodeNode": "48",
      "elk.layered.spacing.nodeNodeBetweenLayers": "80",
    },
    children: tables.map((table) => ({
      id: table.name,
      width: sizes.get(table.name)?.width ?? 240,
      height: sizes.get(table.name)?.height ?? 48,
    })),
    edges: elkEdges,
  });
  return (laid.children ?? []).map((node) => ({
    name: node.id,
    x: node.x ?? 0,
    y: node.y ?? 0,
    width: node.width ?? 240,
    height: node.height ?? 48,
  }));
}
