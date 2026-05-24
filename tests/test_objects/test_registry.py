"""Registry-level test that exercises plugin auto-discovery."""

from __future__ import annotations

from dcmassist.objects import build_registry
from dcmassist.types import V1_TYPES


def test_registry_has_all_v1_plugins() -> None:
    reg = build_registry()
    found = [p.type_name for p in reg.in_canonical_order()]
    assert set(V1_TYPES).issubset(set(found))


def test_unimplemented_plugins_present_too() -> None:
    from dcmassist.types import UNIMPLEMENTED_TYPES

    reg = build_registry()
    found = {p.type_name for p in reg.in_canonical_order()}
    assert set(UNIMPLEMENTED_TYPES).issubset(found)
