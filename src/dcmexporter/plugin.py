"""ObjectPlugin ABC + registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Iterator

from dcmexporter.types import DCM_TYPES, FQN

ProgressCallback = Callable[[str], None]


class ObjectPlugin(ABC):
    type_name: str
    file_slug: str

    @abstractmethod
    def discover(
        self,
        cursor: Any,
        database: str,
        schemas: tuple[str, ...] | None,
        progress: ProgressCallback | None = None,
    ) -> list[FQN]: ...

    @abstractmethod
    def get_ddl(self, cursor: Any, fqn: FQN) -> str: ...

    @abstractmethod
    def to_define_and_invocation(
        self,
        ddl: str,
        *,
        comment: str | None,
        use_macros: bool,
        database: str,
    ) -> str: ...

    @abstractmethod
    def macro_definition(self) -> str: ...


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, ObjectPlugin] = {}

    def register(self, plugin: ObjectPlugin) -> None:
        if plugin.type_name in self._plugins:
            raise ValueError(f"Plugin for {plugin.type_name!r} already registered")
        self._plugins[plugin.type_name] = plugin

    def get(self, type_name: str) -> ObjectPlugin:
        return self._plugins[type_name]

    def has(self, type_name: str) -> bool:
        return type_name in self._plugins

    def in_canonical_order(self) -> Iterator[ObjectPlugin]:
        for type_name in DCM_TYPES:
            if type_name in self._plugins:
                yield self._plugins[type_name]
