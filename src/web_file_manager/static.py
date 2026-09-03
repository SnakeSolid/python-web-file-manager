"""The single-page client: HTML + embedded CSS + embedded vanilla JS.

The page is one self-contained document (no CDN, no build step, no external assets).
It is rendered once per server configuration with the two feature flags (upload /
download) baked into ``<meta>`` tags that the JavaScript reads on load.

The markup lives in ``index.html`` (a sibling of this module) and is loaded at
import time; ``render_index`` bakes the two feature flags into the template.

The favicon is the self-contained ``favicon.svg`` (also a sibling), served as
``image/svg+xml`` at ``/favicon.ico`` so the browser picks it up automatically.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["render_index"]

# Siblings of this module, bundled with the package.
_TEMPLATE_PATH = Path(__file__).with_name("index.html")
_HTML = _TEMPLATE_PATH.read_text(encoding="utf-8")
_FAVICON_PATH = Path(__file__).with_name("favicon.svg")
_FAVICON_BYTES = _FAVICON_PATH.read_bytes()

# Public alias so the route can reference the bytes without reaching into the
# module's private namespace.
FAVICON_BYTES = _FAVICON_BYTES


def render_index(allow_upload: bool, allow_download: bool) -> str:
    """Render the single-page UI with the two feature flags baked in."""
    return _HTML.replace("__UPLOAD__", "true" if allow_upload else "false").replace(
        "__DOWNLOAD__", "true" if allow_download else "false"
    )
