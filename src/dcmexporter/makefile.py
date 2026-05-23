"""Makefile renderer."""

from __future__ import annotations

from dcmexporter.config import Config


def render_makefile(cfg: Config) -> str:
    # Reminder for the parent-schema rule: a DCM project cannot manage the
    # schema it lives in. dcmexporter doesn't know which schema the project
    # is deployed to, so nudge the user to remove the matching DEFINE block.
    # The warning is in its own target so plan and apply share one source.
    warn_line = (
        '\t@echo "[dcmexporter] reminder: if your DCM project lives in '
        "this database, remove the DEFINE for its parent schema from "
        'sources/definitions/schema.sql before running plan/apply."'
    )
    return (
        ".PHONY: warn-parent-schema plan apply\n"
        "\n"
        f"TARGET ?= {cfg.default_target}\n"
        "\n"
        "warn-parent-schema:\n"
        f"{warn_line}\n"
        "\n"
        "plan: warn-parent-schema\n"
        "\tsnow dcm plan --from . --target $(TARGET)\n"
        "\n"
        "apply: warn-parent-schema\n"
        "\tsnow dcm execute --from . --target $(TARGET)\n"
    )
