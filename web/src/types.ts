export type GraphEdge = {
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
  source: string;
  target: string;
  type: "DIRECT" | "INDIRECT";
  subtype: string;
  expression: string;
  file: string;
  line: number;
  statement_id: string;
};

export type TablePayload = {
  name: string;
  columns: string[];
};

export type GraphPayload = {
  view: "column" | "table";
  tables: TablePayload[];
  edges: GraphEdge[];
};

export type ImpactPayload =
  | {
      kind: "change";
      column: string;
      direct: string[];
      indirect: string[];
      evidence: GraphEdge[];
    }
  | {
      kind: "drop";
      column: string;
      failing_statements: string[];
      broken_tables: string[];
      affected_columns: string[];
      evidence: GraphEdge[];
    };

export type SearchHit = {
  fqn: string;
  table: string;
  column: string;
};
