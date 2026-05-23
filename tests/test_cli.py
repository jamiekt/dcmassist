"""Tests for Click CLI argument parsing and validation."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from dcmexporter.cli import cli


def _invoke(args: list[str]) -> tuple[int, str]:
    """Run the CLI with `--database` plumbed through. Patches the orchestrator."""
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        result = runner.invoke(cli, args, catch_exceptions=False)
    return result.exit_code, result.output


def test_export_requires_database() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["export"], catch_exceptions=False)
    assert result.exit_code == 2
    assert "--database" in result.output


def test_export_minimal_invocation() -> None:
    code, _ = _invoke(["export", "--database", "MYDB"])
    assert code == 0


def test_export_invalid_include() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export", "--database", "MYDB", "--include", "Banana"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "Banana" in result.output


def test_export_unimplemented_include() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export", "--database", "MYDB", "--include", "Task"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "not yet supported" in result.output


def test_export_reserved_database_in_templating_default() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export", "--database", "MYDB", "--templating-default", "database=MYDB"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "reserved" in result.output


def test_export_reserved_database_in_templating_configuration_key() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export",
            "--database",
            "MYDB",
            "--configuration",
            "STAGING",
            "--templating-configuration-key",
            "database",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "reserved" in result.output


def test_export_templating_configuration_key_without_configuration() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export",
            "--database",
            "MYDB",
            "--templating-configuration-key",
            "environment",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "--configuration" in result.output


def test_export_malformed_templating_default() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export", "--database", "MYDB", "--templating-default", "no-equals"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "key=value" in result.output


def test_export_passes_normalised_config_to_runner() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        result = runner.invoke(
            cli,
            [
                "export",
                "--database",
                "MYDB",
                "--include",
                "table",
                "--target",
                "staging",
                "--target",
                "live",
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    cfg = run.call_args.args[0]
    assert cfg.database == "MYDB"
    assert cfg.includes == ("Table",)
    assert cfg.targets == ("staging", "live")
    assert cfg.default_target == "staging"


def test_export_default_target_when_none_given() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(cli, ["export", "--database", "MYDB"], catch_exceptions=False)
    cfg = run.call_args.args[0]
    assert cfg.targets == ("start",)
    assert cfg.default_target == "start"


def test_export_use_macros_default_false() -> None:
    """Omitting --use-macros must not generate a sources/macros folder."""
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(cli, ["export", "--database", "MYDB"], catch_exceptions=False)
    cfg = run.call_args.args[0]
    assert cfg.use_macros is False


def test_export_use_macros_opt_in() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(
            cli,
            ["export", "--database", "MYDB", "--use-macros"],
            catch_exceptions=False,
        )
    cfg = run.call_args.args[0]
    assert cfg.use_macros is True


def test_export_empty_comment_kept_as_empty_string() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(
            cli,
            ["export", "--database", "MYDB", "--comment", ""],
            catch_exceptions=False,
        )
    cfg = run.call_args.args[0]
    assert cfg.comment == ""


def test_export_default_comment_includes_url_and_date() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(cli, ["export", "--database", "MYDB"], catch_exceptions=False)
    cfg = run.call_args.args[0]
    assert cfg.comment is not None
    assert "github.com/jamiekt/dcmexporter" in cfg.comment


def test_export_templating_default_json_value_parsed() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(
            cli,
            [
                "export",
                "--database",
                "MYDB",
                "--templating-default",
                'tags={"team":"data"}',
            ],
            catch_exceptions=False,
        )
    cfg = run.call_args.args[0]
    assert cfg.templating_defaults == (("tags", {"team": "data"}),)
