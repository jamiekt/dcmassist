"""Makefile renderer."""

from __future__ import annotations

from dcmexporter.config import Config


def render_makefile(cfg: Config) -> str:
    # Reminder for the parent-schema rule: a DCM project cannot manage the
    # schema it lives in. dcmexporter doesn't know which schema the project
    # is deployed to, so nudge the user to remove the matching DEFINE block
    # before running plan.
    plan_warning = (
        '\t@echo "[dcmexporter] reminder: if your DCM project lives in '
        "this database, remove the DEFINE for its parent schema from "
        'sources/definitions/schema.sql before running plan."'
    )
    return (
        ".PHONY: plan apply\n"
        "\n"
        f"TARGET ?= {cfg.default_target}\n"
        "\n"
        "plan:\n"
        f"{plan_warning}\n"
        "\tsnow dcm plan --from . --target $(TARGET)\n"
        "\n"
        "apply:\n"
        "\tsnow dcm execute --from . --target $(TARGET)\n"
    )
