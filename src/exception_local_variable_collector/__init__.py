"""Exception local variable collector.

Public API:

- :func:`collect_locals` -- capture locals from every frame in an
  exception's traceback into a size-bounded dictionary.
- :class:`Collector` -- reusable collector with configurable limits.
"""

from .core import Collector, collect_locals

__all__ = ["Collector", "collect_locals"]
