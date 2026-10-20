"""Optional bridge: expose VideoAgent components to OpenMontage's tool registry.

OpenMontage is an optional upstream (AGPL-3.0). When it is installed (`make openmontage`),
`register_with_openmontage()` wraps every VideoAgent component so OpenMontage pipelines
can call it. VideoAgent itself never imports OpenMontage at runtime.
"""
from __future__ import annotations

from va.core import discover


def register_with_openmontage() -> int:
    try:
        from openmontage.tools import registry  # type: ignore
    except ImportError:
        return 0
    n = 0
    for name, cls in discover().items():
        if hasattr(registry, "register_external"):
            registry.register_external(name=f"va.{name}", schema=cls.schema(), factory=cls)
            n += 1
    return n
