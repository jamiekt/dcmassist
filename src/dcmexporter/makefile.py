"""Makefile renderer."""

from __future__ import annotations

from dcmexporter.config import Config


def render_makefile(cfg: Config) -> str:
    return (
        ".PHONY: plan apply\n"
        "\n"
        f"TARGET ?= {cfg.default_target}\n"
        "\n"
        "plan:\n"
        "\tsnow dcm plan --from . --target $(TARGET)\n"
        "\n"
        "apply:\n"
        "\tsnow dcm execute --from . --target $(TARGET)\n"
    )
