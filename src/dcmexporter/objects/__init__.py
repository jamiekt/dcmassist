"""Auto-discovered Snowflake DCM object plugins."""

from __future__ import annotations

import importlib
import pkgutil

from dcmexporter.plugin import PluginRegistry


def build_registry() -> PluginRegistry:
    registry = PluginRegistry()
    package = importlib.import_module(__name__)
    for _importer, module_name, _ispkg in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_"):
            # _unimplemented carries a list, _base is just shared code.
            if module_name == "_unimplemented":
                module = importlib.import_module(f"{__name__}.{module_name}")
                for plugin in module.unimplemented_plugins:
                    registry.register(plugin)
            continue
        module = importlib.import_module(f"{__name__}.{module_name}")
        if hasattr(module, "plugin"):
            registry.register(module.plugin)
    return registry
