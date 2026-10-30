"""Grog: offline XAUUSD research and manual decision-support terminal.

Grog is rule-based local software. It contains no AI agent, no broker order
placement and no automated trading.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("grog")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    __version__ = "0+unknown"

__all__ = ["__version__"]
