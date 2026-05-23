"""Tests for Makefile rendering."""

from __future__ import annotations

from pathlib import Path

from dcmexporter.config import Config
from dcmexporter.makefile import render_makefile


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


def test_makefile_uses_default_target() -> None:
    out = render_makefile(_cfg(default_target="start"))
    assert "TARGET ?= start" in out


def test_makefile_uses_first_user_target() -> None:
    out = render_makefile(_cfg(targets=("staging", "live"), default_target="staging"))
    assert "TARGET ?= staging" in out


def test_makefile_has_plan_and_apply() -> None:
    out = render_makefile(_cfg())
    assert "plan:" in out
    assert "apply:" in out
    assert "snow dcm plan --from . --target $(TARGET)" in out
    assert "snow dcm execute --from . --target $(TARGET)" in out


def test_makefile_uses_real_tabs_for_recipes() -> None:
    out = render_makefile(_cfg())
    plan_recipe_lines = [line for line in out.splitlines() if "snow dcm plan" in line]
    assert plan_recipe_lines[0].startswith("\t")
