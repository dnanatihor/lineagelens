import { Background, Controls, ReactFlow, type Edge } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import "@xyflow/react/dist/style.css";

import { highlightColumn, visibleEdges } from "./highlight";
import { layoutTables } from "./layout";
import { TableNode, type TableFlowNode } from "./TableNode";
import type { GraphEdge, GraphPayload, ImpactPayload, SearchHit } from "./types";

const nodeTypes = { table: TableNode };

const SUBTYPES = [
  "IDENTITY",
  "TRANSFORMATION",
  "AGGREGATION",
  "FILTER",
  "JOIN",
  "GROUP_BY",
  "SORT",
  "WINDOW",
  "CONDITIONAL",
];

function edgeId(edge: GraphEdge, index: number): string {
  return `${edge.source}->${edge.target}:${edge.subtype}:${index}`;
}

async function loadGraph(): Promise<GraphPayload> {
  const response = await fetch("/api/graph");
  if (!response.ok) {
    throw new Error("The graph API returned an error.");
  }
  return (await response.json()) as GraphPayload;
}

export function App() {
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showIndirect, setShowIndirect] = useState(true);
  const [subtypes, setSubtypes] = useState<Set<string>>(() => new Set(SUBTYPES));
  const [selected, setSelected] = useState<string | null>(null);
  const [impact, setImpact] = useState<string[]>([]);
  const [panel, setPanel] = useState<GraphEdge | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());

  useEffect(() => {
    loadGraph()
      .then(setGraph)
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Could not load the graph.");
      });
  }, []);

  const shown = useMemo(
    () => (graph === null ? [] : visibleEdges(graph.edges, showIndirect, subtypes)),
    [graph, showIndirect, subtypes],
  );

  useEffect(() => {
    if (graph === null) {
      return;
    }
    let cancelled = false;
    layoutTables(graph.tables, shown, graph.view)
      .then((placed) => {
        if (cancelled) {
          return;
        }
        setPositions(new Map(placed.map((item) => [item.name, { x: item.x, y: item.y }])));
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Layout failed.");
      });
    return () => {
      cancelled = true;
    };
  }, [graph, shown]);

  const highlight = useMemo(
    () => (selected === null ? { upstream: new Set<string>(), downstream: new Set<string>() } : highlightColumn(selected, shown)),
    [selected, shown],
  );

  const onSelect = useCallback((fqn: string) => {
    setSelected(fqn);
    setImpact([]);
    setPanel(null);
  }, []);

  const nodes = useMemo<TableFlowNode[]>(() => {
    if (graph === null) {
      return [];
    }
    return graph.tables.map((table, index) => ({
      id: table.name,
      type: "table",
      position: positions.get(table.name) ?? { x: index * 280, y: 0 },
      data: {
        table: table.name,
        columns: table.columns,
        level: graph.view,
        selected,
        upstream: [...highlight.upstream],
        downstream: [...highlight.downstream],
        impact,
        onSelect,
      },
    }));
  }, [graph, positions, selected, highlight, impact, onSelect]);

  const flowEdges = useMemo<Edge[]>(() => {
    if (graph === null) {
      return [];
    }
    return shown.map((edge, index) => ({
      id: edgeId(edge, index),
      source: edge.source_table,
      target: edge.target_table,
      sourceHandle: graph.view === "column" ? edge.source_column : undefined,
      targetHandle: graph.view === "column" ? edge.target_column : undefined,
      data: edge,
      label: edge.subtype,
    }));
  }, [graph, shown]);

  const openEdge = useCallback((_event: unknown, edge: Edge) => {
    const payload = edge.data as GraphEdge | undefined;
    if (payload) {
      setPanel(payload);
    }
  }, []);

  async function runImpact(kind: "change" | "drop"): Promise<void> {
    if (selected === null) {
      return;
    }
    const response = await fetch(`/api/impact?${kind}=${encodeURIComponent(selected)}`);
    if (!response.ok) {
      setError("Impact lookup failed.");
      return;
    }
    const body = (await response.json()) as ImpactPayload;
    if (body.kind === "change") {
      setImpact([...body.direct, ...body.indirect]);
    } else {
      setImpact(body.affected_columns);
    }
    setPanel(body.evidence[0] ?? null);
  }

  async function search(event: FormEvent): Promise<void> {
    event.preventDefault();
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    if (!response.ok) {
      return;
    }
    const body = (await response.json()) as { results: SearchHit[] };
    setHits(body.results);
  }

  function toggleSubtype(subtype: string): void {
    setSubtypes((current) => {
      const next = new Set(current);
      if (next.has(subtype)) {
        next.delete(subtype);
      } else {
        next.add(subtype);
      }
      return next;
    });
  }

  if (error !== null) {
    return <p role="alert">{error}</p>;
  }
  if (graph === null) {
    return <p>Loading graph…</p>;
  }

  return (
    <div className="app">
      <aside className="toolbar">
        <h1>LineageLens</h1>
        <label>
          <input
            type="checkbox"
            checked={showIndirect}
            onChange={(event) => setShowIndirect(event.target.checked)}
          />
          INDIRECT edges
        </label>
        <fieldset>
          <legend>Subtype</legend>
          {SUBTYPES.map((subtype) => (
            <label key={subtype}>
              <input
                type="checkbox"
                checked={subtypes.has(subtype)}
                onChange={() => toggleSubtype(subtype)}
              />
              {subtype}
            </label>
          ))}
        </fieldset>
        <form onSubmit={(event) => void search(event)}>
          <input
            aria-label="Search columns"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit">Search</button>
        </form>
        <ul>
          {hits.map((hit) => (
            <li key={hit.fqn}>
              <button type="button" onClick={() => onSelect(hit.fqn)}>
                {hit.fqn}
              </button>
            </li>
          ))}
        </ul>
        <button type="button" disabled={selected === null} onClick={() => void runImpact("change")}>
          Impact of change
        </button>
        <button type="button" disabled={selected === null} onClick={() => void runImpact("drop")}>
          Impact of drop
        </button>
        <section aria-label="Edge details">
          {panel === null ? (
            <p>Select an edge to see its expression.</p>
          ) : (
            <>
              <p>{panel.expression}</p>
              <p>
                {panel.file}:{panel.line}
              </p>
            </>
          )}
        </section>
      </aside>
      <div className="canvas">
        <ReactFlow
          nodes={nodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onEdgeClick={openEdge}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
