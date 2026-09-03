"""Path handling: containment checks, relative-path normalization, safe-name sanitization.

Everything in this module is pure (no I/O) except ``resolve``/``unique_name``, which
perform the filesystem lookups required to answer "does this path exist inside the
base directory?". All of them fail *closed* — an invalid or escaping path yields
``None`` rather than an exception, so callers can uniformly turn it into a 404.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

__all__ = ["resolve", "rel_display", "safe_filename", "unique_name"]

# Maximum length of a sanitized filename in UTF-8 bytes.
_MAX_FILENAME_BYTES = 255


def resolve(base_dir: Path, rel: str) -> Path | None:
    """Resolve a request-supplied relative path against ``base_dir``.

    URL-decodes ``rel``, strips any leading slash, forbids NUL bytes, resolves the
    absolute path with :func:`os.path.realpath` and verifies the result is
    ``base_dir`` itself or contained within it. Returns the resolved :class:`Path`
    or ``None`` when the path is malformed or escapes the base directory.
    """
    if rel is None:
        return None
    try:
        decoded = urllib.parse.unquote(rel)
    except (TypeError, ValueError):
        return None
    if "\x00" in decoded:
        return None
    # Strip leading slash(es) and forward-slashes are normalized by Path joining.
    rel_norm = decoded.lstrip("/")
    candidate = (base_dir / rel_norm) if rel_norm else base_dir
    resolved = Path(os.path.realpath(candidate))
    base_resolved = Path(os.path.realpath(base_dir))
    if resolved == base_resolved:
        return resolved
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        return None
    return resolved


def rel_display(path: Path, base_dir: Path) -> str:
    """Return the forward-slash-normalized relative path of ``path`` under ``base_dir``.

    Empty string for the base directory itself.
    """
    try:
        rel = os.path.relpath(path, os.path.realpath(base_dir))
    except ValueError:
        return ""
    if rel in (".", ""):
        return ""
    return rel.replace(os.sep, "/")


def safe_filename(name: str) -> str | None:
    """Sanitize an uploaded filename to a single safe component.

    Takes :func:`os.path.basename`, strips NUL and control characters, truncates to
    255 UTF-8 bytes at a character boundary, and returns ``None`` if nothing
    meaningful remains.
    """
    if not name:
        return None
    base = os.path.basename(name.replace("\\", "/"))
    # Strip NUL and control characters (C0 + DEL + C1 range).
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", base)
    if not cleaned:
        return None
    # Truncate to 255 UTF-8 bytes without splitting a multi-byte character.
    encoded = cleaned.encode("utf-8")
    if len(encoded) > _MAX_FILENAME_BYTES:
        cut = encoded[:_MAX_FILENAME_BYTES]
        cleaned = cut.decode("utf-8", errors="ignore")
        # Fall back to a shorter prefix if the decode yields nothing (very unlikely).
        if not cleaned:
            cleaned = cut.rstrip().decode("utf-8", errors="ignore")
    if not cleaned:
        return None
    return cleaned


def unique_name(directory: Path, name: str) -> Path:
    """Return a collision-free destination path for ``name`` inside ``directory``.

    Implements the ``name.ext`` → ``name (1).ext`` → … collision policy. The returned
    path is guaranteed not to exist (barring a racing process).
    """
    target = directory / name
    if not target.exists():
        return target
    stem, dot, ext = _split_ext(name)
    index = 1
    while True:
        candidate_name = f"{stem} ({index}){dot}{ext}" if dot else f"{stem} ({index})"
        target = directory / candidate_name
        if not target.exists():
            return target
        index += 1


def _split_ext(name: str) -> tuple[str, str, str]:
    """Split ``name`` into (stem, dot, ext) so reassembly preserves the dot.

    A leading-dot dotfile such as ``.env`` has no extension (stem = ``.env``).
    """
    if "." not in name:
        return name, "", ""
    stem, dot, ext = name.rpartition(".")
    if stem == "":
        # Leading dot only, e.g. ".env" -> no extension.
        return name, "", ""
    return stem, dot, ext
