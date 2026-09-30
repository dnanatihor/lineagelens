"""The CLI skeleton exposes the §7 commands and rejects invalid flags."""

from __future__ import annotations

from typer.testing import CliRunner

from lineagelens.cli import app

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


def test_unimplemented_commands_exit_2() -> None:
    result = runner.invoke(app, ["build", "tests/fixtures/warehouse"])
    assert result.exit_code == 2
    assert "not implemented" in result.stderr
