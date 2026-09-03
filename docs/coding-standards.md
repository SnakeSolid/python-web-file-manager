# Coding Conventions

These are the conventions the codebase follows. Check this file before committing a
change.

## General

- **Python ≥ 3.12**, `from __future__ import annotations` in every module.
- **Type-hint everything** — function signatures and non-trivial locals. JSON-shaped
  values use `dict[str, Any]` (not bare `dict`).
- **`uv` is the only build/environment tool.** Do not add `pip`/`poetry`/`hatch`
  workflows. Dependencies live in `pyproject.toml`; the lock is `uv.lock`.
- **Stdlib + FastAPI/Starlette objects over manual ASGI plumbing.** Prefer FastAPI
  routing, parameters, responses, middleware, and exception handlers to raw
  ASGI. Hand-rolled code is limited to the two places the framework does not cover
  (body-cap middleware, per-file upload store loop).
- **No new runtime dependencies** without a spec revision (spec §9). The current set
  is exactly `fastapi`, `uvicorn[standard]`, `python-multipart`.

## Structure

- Keep the module roles in
  [architecture.md](./architecture.md) intact: `__init__.py` (CLI + `main`),
  `config.py` (frozen `Config`), `server.py` (app factory), `paths.py` (pure path
  helpers), `static.py` (UI template loading/rendering). Put new behaviour in the
  module that owns it. The single-page UI markup lives in `index.html` (a sibling
  of `static.py`, shipped as package data) and is loaded at import time.
- `main()` is the `uv` script entry — **preserve its signature**
  (`web-file-manager = "web_file_manager:main"`).
- `create_app(config)` is the single factory; inject config via the `Config`
  parameter, not globals.

## Error handling

- **Fail closed.** `paths.resolve` returns `None` for anything invalid or escaping;
  callers convert that to 404. Never return 400 for a path alone.
- Errors that map to an HTTP status are raised as `fastapi.HTTPException(status,
  detail)` and answered by the registered exception handler as JSON
  `{"error": "<detail>"}`.
- **Middleware must return a `Response`, not raise**, to produce a clean status:
  Starlette's `BaseHTTPMiddleware` does not translate raised exceptions into
  responses (a raise there surfaces as 500). The 413 body-cap middleware follows
  this.
- The process must **never crash on a bad request**; request-scoped failures are
  answered and the server keeps serving.
- CLI validation failures (bad base dir, bad port, unbindable address) **exit 2**
  with a message to stderr.

## Conventions for specific areas

- **Uploads**: stream to a temp file in the target dir, then `os.replace`; never
  write the final name directly (avoids symlink follow/overwrite). On I/O error,
  delete the temp file, continue with the remaining files, and record a per-file
  error (partial-failure semantics — the batch is still HTTP 200).
- **Listing**: directories first then files, each case-insensitive alphabetical
  (`key=str.lower`); `.`/`..` are never listed (the UI renders `..` from `parent`).
- **Static UI**: one self-contained HTML document, no external fonts/icons/CDN; the
  two feature flags are baked into `<meta>` tags the JS reads on load.

## Style & lint

- Follow PEP 8; the project keeps functions small and single-purpose.
- Keep docstrings on public functions (module docstring + short function
  docstrings). Comment only non-obvious intent/constraints, not restatements.
- No dead imports, no unused `noqa` directives for lint codes that aren't active in
  this project.
- Keep the `docs/` reference set in sync with any change (see `AGENTS.md`): update
  the relevant document whenever you add/remove/modify a feature.
