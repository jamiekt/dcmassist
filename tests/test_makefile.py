"""Tests for Makefile rendering."""

from __future__ import annotations

from pathlib import Path

from dcmassist.config import Config
from dcmassist.makefile import render_makefile


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


def test_makefile_warns_about_parent_schema_for_plan_and_apply() -> None:
    """Both plan and apply must print the warning so users know to drop the
    DEFINE for the schema their DCM project lives in (DCM rejects 'Project
    cannot manage its parent schema'). The warning is in its own target that
    plan and apply depend on, so the message stays single-sourced."""
    out = render_makefile(_cfg())
    assert "parent schema" in out
    assert "DEFINE" in out
    lines = out.splitlines()
    plan_line = next(line for line in lines if line.startswith("plan:"))
    apply_line = next(line for line in lines if line.startswith("apply:"))
    # The dep name is whatever target carries the warning; require both to
    # name the same dependency.
    plan_deps = plan_line.split(":", 1)[1].split()
    apply_deps = apply_line.split(":", 1)[1].split()
    assert plan_deps, "plan target must declare a prerequisite"
    assert plan_deps == apply_deps, (
        f"plan and apply must share the same warning prerequisite, "
        f"got plan={plan_deps} apply={apply_deps}"
    )
