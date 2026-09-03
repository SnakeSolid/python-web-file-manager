# Architecture & Design

A single-process FastAPI (ASGI) application. This document explains the package
layout, how the pieces fit together, the concurrency model, and the security
guarantees. For *what* the API does, see [specification.md](./specification.md);
this file explains *how* it is built.

## Package layout

```
src/web_file_manager/
  __init__.py        # main(): argparse CLI, config build, uvicorn.run(app)
  __main__.py        # `python -m web_file_manager` entry (thin -> main())
  config.py          # Config dataclass (frozen): base dir, flags, rendered index
  server.py          # create_app(config): FastAPI app — routes, middleware, handlers
  paths.py           # containment check, relpath normalize, safe-name sanitize
  static.py          # loads the single-page UI template, bakes in the two flags
  index.html         # the single-page UI template (HTML/CSS/JS), shipped as package data
```

`main()` (in `__init__.py`) is the `uv` script entry. It:

1. Parses args (`_build_parser`), resolves/validates the base dir (`_resolve_base_dir`
   → exit 2 on failure).
2. Renders the index page (`static.render_index`) and builds a frozen `Config`.
3. Prints the startup banner (and a stderr warning if both flags are off).
4. Probes the bind (`_check_bind` → exit 2 on failure), then
   `uvicorn.run(create_app(config), host, port)`. A bind error that slips past the
   probe is caught and re-raised as exit 2.

Uvicorn is run **directly on the built `FastAPI` instance** (not on an import
string), so config is injected at build time — there is no global app state to read
back.

## Request flow

```
                ┌─────────────────────────── create_app(config) ───────────────────────────┐
  HTTP  ──►  Uvicorn (uvloop)  ──►  FastAPI  ──►  middleware  ──►  route handler  ──►  response
                (threads per conn)     (routes)     (_no_store,      (GET /, /favicon.ico,
                                                 _body_cap)          /list, /file,        (FileResponse /
                                                                     /download,            Redirect / JSON /
                                                                     POST /upload)        HTMLResponse)
```

Each request is handled by an async handler that computes its own path containment
checks. There is **no shared mutable state** between requests; the only shared
objects are the immutable `Config` and the (pure) `paths` helpers.

### Routes

| Method | Path | Behaviour |
|---|---|---|
| GET, HEAD | `/` | Rendered single-page UI (HEAD → empty body, same headers). |
| GET | `/favicon.ico` | Self-contained SVG tab icon (`image/svg+xml`); always available, not feature-gated. |
| GET | `/list?path=` | JSON directory listing; each file entry carries a `mime` field (403 if download disabled, 404 if outside/not-a-dir). |
| GET | `/download?path=` | 302 → `/file?path=...` (403/404). |
| GET | `/file?path=` | File contents, streamed, `Content-Disposition: attachment` (403/404). |
| POST | `/upload` | Multipart `files` + `path` → store in target dir (403/400/413, partial-failure results). |

Middleware (both run on every request):

- `_no_store` — sets `Cache-Control: no-store` on every response **except** `/file`.
- `_body_cap` — rejects POST bodies whose `Content-Length` exceeds the 100 MiB cap
  with **413** *before* the body is parsed (returns a `Response` directly, because
  Starlette's `BaseHTTPMiddleware` does not translate raised exceptions into responses).
  A second, in-handler guard covers chunked bodies (no `Content-Length`) by checking
  the summed file sizes.

Exception handlers:

- `HTTPException` → JSON `{"error": "<detail>"}`.
- `RequestValidationError` → remapped 422 → **400** (bad/missing form data).

## Concurrency & startup

- Uvicorn uses a **thread per connection** and an **async** handler per request,
  on the `uvloop` event loop (from `uvicorn[standard]`).
- Handlers are `async def`; all filesystem work is bounded and streamed (1 MiB
  chunks) so a request never holds a large buffer.
- Startup: `uvicorn.run(app, host, port)` binds the socket; the app is created
  once and handed over. Uvicorn handles `SIGINT`/`SIGTERM` (graceful drain, exit 0).
- The server never crashes on a bad request: request-scoped exceptions are answered
  (4xx/5xx) and the process continues.

## Security model (how it is enforced)

All path handling funnels through `paths.py`, which **fails closed**:

- `resolve(base_dir, rel)` — URL-decode, strip leading `/`, reject NUL,
  `os.path.realpath(base / rel)`, then require the result to equal or be contained
  in `realpath(base_dir)`. Anything that fails → `None` → **404** (never 400, so
  "exists" vs "outside" are not distinguished). This neutralizes `..` traversal,
  absolute paths, and symlinks that point outside the base dir.
- `safe_filename(name)` — `os.path.basename`, strip NUL/control chars, truncate to
  255 UTF-8 bytes at a char boundary; empty → `None` ("invalid filename").
- `unique_name(dir, name)` — collision policy `name.ext` → `name (1).ext` → …
  (first free index).
- `rel_display(path, base_dir)` — forward-slash relative string for API/UI.

Uploads never follow symlinks: each file is written to a **temp file in the same
target directory** and `os.replace`d into place, so a symlink can't be
followed/overwritten with a regular file (TOCTOU-safe).

## Response conventions

- JSON: `application/json; charset=utf-8`; errors are `{"error": "<message>"}`.
- `Cache-Control: no-store` on everything except `/file`.
- `/file` sets `Content-Type` (via `mimetypes`, fallback `application/octet-stream`),
  `Content-Length`, `Content-Disposition: attachment`, and `Accept-Ranges: bytes`
  (byte-range support itself is a v1 non-goal).
- 405 (with `Allow`) for wrong methods and 404 for unmatched paths come from
  Starlette out of the box.
