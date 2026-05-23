"""Tests for the ObjectPlugin ABC and PluginRegistry."""

from __future__ import annotations

import pytest

from dcmexporter.plugin import ObjectPlugin, PluginRegistry


class _FakePlugin(ObjectPlugin):
    type_name = "Table"
    file_slug = "table"

    def discover(self, cursor, database, schemas):
        return []

    def get_ddl(self, cursor, fqn):
        return ""

    def to_define_and_invocation(self, ddl, *, comment, use_macros, database):
        return ""

    def macro_definition(self) -> str:
        return ""


def test_registry_register_and_get() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin()
    reg.register(plugin)
    assert reg.get("Table") is plugin


def test_registry_double_register_raises() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_FakePlugin())


def test_registry_get_unknown_raises() -> None:
    reg = PluginRegistry()
    with pytest.raises(KeyError):
        reg.get("Banana")


def test_registry_iteration_order_matches_v1_types() -> None:
    from dcmexporter.types import V1_TYPES

    class _P(ObjectPlugin):
        def __init__(self, name: str) -> None:
            self.type_name = name
            self.file_slug = name.lower().replace(" ", "_")

        def discover(self, cursor, database, schemas):
            return []

        def get_ddl(self, cursor, fqn):
            return ""

        def to_define_and_invocation(self, ddl, *, comment, use_macros, database):
            return ""

        def macro_definition(self) -> str:
            return ""

    reg = PluginRegistry()
    # Register in reverse order to confirm canonical ordering wins.
    for name in reversed(V1_TYPES):
        reg.register(_P(name))

    assert tuple(p.type_name for p in reg.in_canonical_order()) == V1_TYPES
