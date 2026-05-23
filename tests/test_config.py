"""Tests for the Config dataclass and parsing helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcmexporter.config import (
    Config,
    parse_templating_default,
    resolve_default_target,
    validate_config,
)


def test_parse_templating_default_string() -> None:
    assert parse_templating_default("alliance=unspecified") == (
        "alliance",
        "unspecified",
    )


def test_parse_templating_default_json_object() -> None:
    key, value = parse_templating_default('tags={"team":"data"}')
    assert key == "tags"
    assert value == {"team": "data"}


def test_parse_templating_default_json_number() -> None:
    assert parse_templating_default("retention=7") == ("retention", 7)


def test_parse_templating_default_missing_equals_raises() -> None:
    with pytest.raises(ValueError, match="key=value"):
        parse_templating_default("nope")


def test_parse_templating_default_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_templating_default("=foo")


def test_resolve_default_target_no_targets() -> None:
    assert resolve_default_target([]) == ("start", ("start",))


def test_resolve_default_target_with_targets() -> None:
    assert resolve_default_target(["staging", "live"]) == (
        "staging",
        ("staging", "live"),
    )


def _base_config(**overrides) -> Config:
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


def test_validate_config_rejects_database_in_templating_default() -> None:
    cfg = _base_config(templating_defaults=(("database", "MYDB"),))
    with pytest.raises(ValueError, match="reserved"):
        validate_config(cfg)


def test_validate_config_rejects_database_in_templating_configuration_key() -> None:
    cfg = _base_config(
        configurations=("STAGING",),
        templating_configuration_keys=("database",),
    )
    with pytest.raises(ValueError, match="reserved"):
        validate_config(cfg)


def test_validate_config_rejects_keys_without_configurations() -> None:
    cfg = _base_config(templating_configuration_keys=("environment",))
    with pytest.raises(ValueError, match="--configuration"):
        validate_config(cfg)


def test_validate_config_rejects_unknown_include() -> None:
    cfg = _base_config(includes=("Banana",))
    with pytest.raises(ValueError, match="Banana"):
        validate_config(cfg)


def test_validate_config_rejects_unimplemented_include() -> None:
    cfg = _base_config(includes=("Task",))
    with pytest.raises(ValueError, match="not yet supported"):
        validate_config(cfg)


def test_validate_config_normalises_includes() -> None:
    cfg = _base_config(includes=("table", "VIEW"))
    validated = validate_config(cfg)
    assert validated.includes == ("Table", "View")


def test_validate_config_normalises_excludes() -> None:
    cfg = _base_config(excludes=("sequence",))
    validated = validate_config(cfg)
    assert validated.excludes == ("Sequence",)
