"""Frozen Config dataclass + CLI value parsing/validation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dcmassist.types import UNIMPLEMENTED_TYPES, V1_TYPES, normalise_type


@dataclass(frozen=True)
class Config:
    database: str
    schemas: tuple[str, ...]
    connection: str | None
    targets: tuple[str, ...]
    default_target: str
    templating_defaults: tuple[tuple[str, Any], ...]
    configurations: tuple[str, ...]
    templating_configuration_keys: tuple[str, ...]
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    comment: str | None
    use_macros: bool
    out_folder: Path
    force: bool


def parse_templating_default(raw: str) -> tuple[str, Any]:
    """Parse a `key=value` string. value is JSON-parsed if valid, else kept as a string."""
    if "=" not in raw:
        raise ValueError(
            f"--templating-default must be in key=value form, got: {raw!r}"
        )
    key, _, value = raw.partition("=")
    if not key:
        raise ValueError(f"--templating-default key is empty in: {raw!r}")
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    return key, parsed


def resolve_default_target(
    user_targets: list[str] | tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    """Return (default_target, targets_tuple) given the user-supplied --target list."""
    if not user_targets:
        return "start", ("start",)
    return user_targets[0], tuple(user_targets)


def validate_config(cfg: Config) -> Config:
    """Apply cross-field validation; return a normalised Config or raise ValueError."""
    for key, _ in cfg.templating_defaults:
        if key == "database":
            raise ValueError("'database' is a reserved key for --templating-default")
    for key in cfg.templating_configuration_keys:
        if key == "database":
            raise ValueError(
                "'database' is a reserved key for --templating-configuration-key"
            )
    if cfg.templating_configuration_keys and not cfg.configurations:
        raise ValueError(
            "--templating-configuration-key requires at least one --configuration"
        )

    def _normalise(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(normalise_type(v) for v in values)

    includes = _normalise(cfg.includes)
    excludes = _normalise(cfg.excludes)

    for value in includes:
        if value in UNIMPLEMENTED_TYPES:
            raise ValueError(
                f"Type {value!r} is in DCM's supported set but not yet supported "
                "by dcmassist"
            )

    return replace(cfg, includes=includes, excludes=excludes)


def filter_types(cfg: Config) -> tuple[str, ...]:
    """Resolve the final list of v1 types to export, after include/exclude."""
    if cfg.includes:
        return cfg.includes
    return tuple(t for t in V1_TYPES if t not in cfg.excludes)
