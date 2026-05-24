"""Stub plugins for DCM types that are not yet supported by dcmassist."""

from __future__ import annotations

from typing import Any

from dcmassist.plugin import ObjectPlugin, ProgressCallback
from dcmassist.types import UNIMPLEMENTED_TYPES, FQN


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_")


class _UnimplementedPlugin(ObjectPlugin):
    def __init__(self, type_name: str) -> None:
        self.type_name = type_name
        self.file_slug = _slug(type_name)

    def discover(
        self,
        cursor: Any,
        database: str,
        schemas: tuple[str, ...] | None,
        progress: ProgressCallback | None = None,
    ) -> list[FQN]:
        raise NotImplementedError(
            f"{self.type_name} is in DCM's supported set but not yet implemented "
            "by dcmassist"
        )

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        raise NotImplementedError(self.type_name)

    def to_define_and_invocation(
        self,
        ddl: str,
        *,
        comment: str | None,
        use_macros: bool,
        database: str,
        known_schemas: frozenset[str] = frozenset(),
        known_functions: dict[str, str] | None = None,
    ) -> str:
        raise NotImplementedError(self.type_name)

    def macro_definition(self) -> str:
        raise NotImplementedError(self.type_name)


unimplemented_plugins = [_UnimplementedPlugin(t) for t in UNIMPLEMENTED_TYPES]
