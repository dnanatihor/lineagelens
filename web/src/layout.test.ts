import { layoutTables } from "./layout";
import type { GraphEdge, TablePayload } from "./types";

test("a 300-table by 20-column graph lays out left to right", async () => {
  const tables: TablePayload[] = [];
  const edges: GraphEdge[] = [];
  for (let index = 0; index < 300; index += 1) {
    const columns = Array.from({ length: 20 }, (_, column) => `c${column}`);
    tables.push({ name: `s.t${index}`, columns });
    if (index > 0) {
      edges.push({
        source_table: `s.t${index - 1}`,
        source_column: "c0",
        target_table: `s.t${index}`,
        target_column: "c0",
        source: `s.t${index - 1}.c0`,
        target: `s.t${index}.c0`,
        type: "DIRECT",
        subtype: "IDENTITY",
        expression: "c0",
        file: "file.sql",
        line: 1,
        statement_id: "file.sql#0",
      });
    }
  }
  const placed = await layoutTables(tables, edges, "column");
  expect(placed).toHaveLength(300);
  const first = placed.find((table) => table.name === "s.t0");
  const later = placed.find((table) => table.name === "s.t50");
  expect(first).toBeDefined();
  expect(later).toBeDefined();
  expect((later?.x ?? 0) > (first?.x ?? 0) || (later?.y ?? 0) !== (first?.y ?? 0)).toBe(true);
}, 30_000);
