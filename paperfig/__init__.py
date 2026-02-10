from __future__ import annotations

__all__ = ["__version__"]

try:
    from importlib.metadata import version

    __version__ = version("paperfigg")
except Exception:
    __version__ = "0.4.0"
