import type { GraphEdge } from "./types";

export type Highlight = {
  upstream: Set<string>;
  downstream: Set<string>;
};

export function visibleEdges(
  edges: GraphEdge[],
  showIndirect: boolean,
  subtypes: ReadonlySet<string>,
): GraphEdge[] {
  return edges.filter((edge) => {
    if (!showIndirect && edge.type === "INDIRECT") {
      return false;
    }
    return subtypes.has(edge.subtype);
  });
}

export function highlightColumn(column: string, edges: GraphEdge[]): Highlight {
  const downstream = new Set<string>();
  const upstream = new Set<string>();
  const forward = new Map<string, string[]>();
  const backward = new Map<string, string[]>();
  for (const edge of edges) {
    const outs = forward.get(edge.source) ?? [];
    outs.push(edge.target);
    forward.set(edge.source, outs);
    const ins = backward.get(edge.target) ?? [];
    ins.push(edge.source);
    backward.set(edge.target, ins);
  }
  walk(column, forward, downstream);
  walk(column, backward, upstream);
  return { upstream, downstream };
}

function walk(start: string, adjacency: Map<string, string[]>, found: Set<string>): void {
  const pending = [...(adjacency.get(start) ?? [])];
  const seen = new Set<string>([start]);
  while (pending.length > 0) {
    const next = pending.pop();
    if (next === undefined || seen.has(next)) {
      continue;
    }
    seen.add(next);
    found.add(next);
    pending.push(...(adjacency.get(next) ?? []));
  }
}
