"""Export one OpenLineage dataset per target table."""

from __future__ import annotations

import json
from collections import defaultdict

from lineagelens.graph import LineageGraph
from lineagelens.models import Edge

_PRODUCER = "https://github.com/dnanatihor/lineagelens"
_SCHEMA_URL = "https://openlineage.io/spec/facets/1-2-0/ColumnLineageDatasetFacet.json"
_NAMESPACE = "lineagelens"


def export_openlineage(graph: LineageGraph) -> str:
    by_target: dict[str, dict[str, list[Edge]]] = defaultdict(lambda: defaultdict(list))
    for edge in graph.edges:
        by_target[_table_name(edge.target)][edge.target.column].append(edge)
    datasets = []
    for table_name in sorted(by_target):
        fields = {}
        for column in sorted(by_target[table_name]):
            inputs = []
            for edge in sorted(
                by_target[table_name][column],
                key=lambda item: (item.source.fqn(), item.type, item.subtype),
            ):
                inputs.append(
                    {
                        "namespace": _NAMESPACE,
                        "name": _table_name(edge.source),
                        "field": edge.source.column,
                        "transformations": [{"type": edge.type, "subtype": edge.subtype}],
                    }
                )
            fields[column] = {"inputFields": inputs}
        datasets.append(
            {
                "namespace": _NAMESPACE,
                "name": table_name,
                "facets": {
                    "columnLineage": {
                        "_producer": _PRODUCER,
                        "_schemaURL": _SCHEMA_URL,
                        "fields": fields,
                    }
                },
            }
        )
    return json.dumps({"datasets": datasets}, indent=2) + "\n"


def _table_name(column: object) -> str:
    from lineagelens.models import ColumnRef

    if not isinstance(column, ColumnRef):
        message = "expected a column reference"
        raise TypeError(message)
    parts = [part for part in (column.database, column.schema_, column.table) if part is not None]
    return ".".join(parts)
