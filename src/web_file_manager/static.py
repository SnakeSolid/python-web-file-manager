"""The single-page client: HTML + embedded CSS + embedded vanilla JS.

The page is one self-contained document (no CDN, no build step, no external assets).
It is rendered once per server configuration with the two feature flags (upload /
download) baked into ``<meta>`` tags that the JavaScript reads on load.

The markup lives in ``index.html`` (a sibling of this module) and is loaded at
import time; ``render_index`` bakes the two feature flags into the template.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["render_index"]

# Sibling of this module, bundled with the package.
_TEMPLATE_PATH = Path(__file__).with_name("index.html")
_HTML = _TEMPLATE_PATH.read_text(encoding="utf-8")


def render_index(allow_upload: bool, allow_download: bool) -> str:
    """Render the single-page UI with the two feature flags baked in."""
    return _HTML.replace("__UPLOAD__", "true" if allow_upload else "false").replace(
        "__DOWNLOAD__", "true" if allow_download else "false"
    )
