"""Runtime configuration shared by the CLI, the ASGI app, and the request handlers.

A single immutable :class:`Config` value is built once from the CLI arguments and
attached to the app via ``app.state``. Request handlers read only from it, so there
is no shared mutable state between requests (spec §6.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["Config"]


@dataclass(frozen=True)
class Config:
    """Immutable server configuration resolved from the CLI arguments."""

    base_dir: Path  # absolute, real-pathed base directory to expose
    allow_upload: bool
    allow_download: bool
    index_html: str  # rendered single-page UI (static per configuration)
