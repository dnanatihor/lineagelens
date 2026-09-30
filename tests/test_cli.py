"""The CLI skeleton exposes the §7 commands and rejects invalid flags."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from lineagelens.cli import app
from lineagelens.export.json import export_json
from lineagelens.project import build_project

WAREHOUSE = Path("tests/fixtures/warehouse")

runner = CliRunner()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("build", "impact", "export", "serve", "ask"):
        assert name in result.stdout


def test_impact_requires_exactly_one_mode() -> None:
    missing = runner.invoke(app, ["impact", "graph.json"])
    assert missing.exit_code == 2
    both = runner.invoke(
        app,
        ["impact", "graph.json", "--change", "raw.orders.id", "--drop", "raw.orders.id"],
    )
    assert both.exit_code == 2


def test_export_rejects_unknown_format() -> None:
    result = runner.invoke(app, ["export", "graph.json", "--format", "csv"])
    assert result.exit_code == 2


def test_ask_is_not_implemented_yet() -> None:
    ask = runner.invoke(app, ["ask", "graph.json", "what breaks?"])
    assert ask.exit_code == 2
    assert "not implemented" in ask.stderr


def test_serve_loads_the_warehouse_graph(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text(export_json(build_project([WAREHOUSE])), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(server_app: object, *, host: str, port: int) -> None:
        captured["app"] = server_app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("lineagelens.cli.uvicorn.run", fake_run)
    result = runner.invoke(app, ["serve", str(graph), "--port", "8765"])
    assert result.exit_code == 0
    assert captured["port"] == 8765
    client = TestClient(captured["app"])  # type: ignore[arg-type]
    payload = client.get("/api/graph").json()
    assert any(table["name"] == "staging.stg_orders" for table in payload["tables"])
