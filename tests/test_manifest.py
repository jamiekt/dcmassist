"""Tests for manifest.yml rendering."""

from __future__ import annotations

from pathlib import Path

from dcmassist.config import Config
from dcmassist.manifest import render_manifest


def _cfg(**overrides) -> Config:
    base = dict(
        database="MYDB",
        schemas=(),
        connection=None,
        targets=("start",),
        default_target="start",
        templating_defaults=(),
        configurations=(),
        templating_configuration_keys=(),
        includes=(),
        excludes=(),
        comment=None,
        use_macros=True,
        out_folder=Path("out"),
        force=False,
    )
    base.update(overrides)
    return Config(**base)


def test_manifest_default_start_target_no_configurations() -> None:
    out = render_manifest(_cfg(), account_identifier="AB12345")
    assert "manifest_version: 2" in out
    assert "type: DCM_PROJECT" in out
    assert "  start:" in out
    assert "    account_identifier: AB12345" in out
    assert "    project_name: MYDB.PUBLIC.MAIN" in out
    assert '    project_owner: ""' in out
    assert "templating_config:" not in out
    # database lives under templating.defaults when no --configuration
    assert "  defaults:" in out
    assert "    # Probably change this" in out
    assert "    database: MYDB" in out


def test_manifest_multiple_targets_no_start() -> None:
    cfg = _cfg(targets=("staging", "live"), default_target="staging")
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "  staging:" in out
    assert "  live:" in out
    assert "  start:" not in out


def test_manifest_with_configurations_includes_templating_config_per_target() -> None:
    cfg = _cfg(
        configurations=("STAGING", "LIVE"),
        targets=("staging", "live"),
        default_target="staging",
    )
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "    templating_config: staging" in out
    assert "    templating_config: live" in out


def test_manifest_with_configurations_database_in_each_block() -> None:
    cfg = _cfg(
        configurations=("STAGING", "LIVE"),
        templating_configuration_keys=("environment",),
    )
    out = render_manifest(cfg, account_identifier="AB12345")
    # database appears under each configuration, with the leading comment
    assert out.count("# Probably change this") == 2
    assert out.count("database: MYDB") == 2
    # configurations block contains environment: ""
    assert "environment: ''" in out or 'environment: ""' in out


def test_manifest_templating_defaults_string_value() -> None:
    cfg = _cfg(templating_defaults=(("alliance", "unspecified"),))
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "alliance: unspecified" in out


def test_manifest_templating_defaults_json_object_value() -> None:
    cfg = _cfg(templating_defaults=(("tags", {"team": "data"}),))
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "tags:" in out
    assert "team: data" in out


def test_manifest_account_identifier_blank_when_missing() -> None:
    out = render_manifest(_cfg(), account_identifier="")
    assert 'account_identifier: ""' in out


def test_manifest_top_level_key_order() -> None:
    out = render_manifest(_cfg(), account_identifier="AB12345")
    lines = [line for line in out.splitlines() if line and not line.startswith(" ")]
    # header comments may appear; filter to top-level YAML keys
    keys = [
        line.split(":", 1)[0]
        for line in lines
        if ":" in line and not line.startswith("#")
    ]
    # Expect manifest_version, type, targets, templating in this order
    assert keys[:4] == ["manifest_version", "type", "targets", "templating"]
