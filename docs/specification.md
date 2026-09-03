# Web File Manager — Functional Specification

**Version**: 1.1 (server stack: Uvicorn + FastAPI)
**Status**: Approved for implementation
**Date**: 2026-09-02

---

## 1. Overview

A single-process Python web service that exposes a directory tree as a browser-based file manager. Users can walk the directory tree and download files; optionally they can upload files into any visible directory. The whole thing is a self-contained script started from the CLI, with no external services, no databases, and no client-side network dependencies.

**Hard requirements:**

- The server is a **Uvicorn** (`uvicorn[standard]`) ASGI app built with **FastAPI**.
- **Prefer FastAPI objects** (routing, parameters, responses, middleware, exceptions) over raw stdlib / manual ASGI plumbing whenever practical.
- Pure **HTML + CSS + vanilla JS** for the client (single page, no CDN, no build step, no external assets).
- Dependencies are managed with **`uv`** (project already uses `uv` + `uv_build`); the package adds the runtime dependencies listed in §9.
- No automated tests for this project (explicitly excluded from scope).
- The service listens on a configurable address/port and serves **only** files under a configurable base directory. Nothing outside the base directory is ever readable, writable, or listable.

## 2. CLI

Entry point: `web-file-manager` (project script) ≡ `python -m web_file_manager`.

Uses `argparse`:

| Flag(s) | Dest | Default | Description |
|---|---|---|---|
| `--address`, `-a` | `address` | `localhost` | Bind address (host name or IP). |
| `--port`, `-p` | `port` | `8080` | TCP port. |
| `--base-dir`, `-d` | `base_dir` | `.` | Directory to expose (resolved to an absolute path). |
| `--allow-upload` | `allow_upload` | `false` | Enable upload endpoints. |
| `--allow-download` | `allow_download` | `false` | Enable file listing / download. |

Start-up validation:

1. `base_dir` must exist and be a directory → else print `error: base directory '<path>' does not exist or is not a directory` and exit **2**.
2. Port in range 1–65535 (argparse `type` enforces).
3. Address bound: bind failure → print the bind error, exit **2**.
4. Both `--allow-upload` and `--allow-download` are `false` → still start (server returns 404 for everything) and log a warning. Not an error — the operator may rely on that.

**Startup log lines** (to stdout, plain text, no framework):

```
Web file manager: http://<address>:<port>/
Base directory: <abs path>
Upload enabled: yes|no
Download enabled: yes|no
```

Afterwards the process blocks until `SIGINT`/`SIGTERM`; the handler prints `Shutting down...` and exits 0. Unhandled request errors are logged to stderr with a timestamp; the server never crashes on a bad request.

## 3. Security Model

1. **Path containment.** Every request path is URL-decoded, converted to a path relative to the base directory, resolved against it (`os.path.realpath`), and the result must start with `realpath(base_dir)` + separator. Any request that fails this check → **404** (not 400, to avoid distinguishing "exists" from "outside"). `..` traversal, absolute paths, and backslashes are neutralized by this check; the server **never** rejects with 400 on a path alone — it just 404s.
2. **No directory escape on uploads.** Same containment rule applies to the upload target directory; uploading "into" a path outside the base directory is impossible.
3. **No file metadata or content is ever served for paths outside the base directory**, including symlink resolution — a symlink inside the base dir that points outside resolves to an absolute path, fails containment, and is not served.
4. **Uploads never follow symlinks.** When creating the destination file the server writes to a **temporary file in the same target directory** and `os.replace`s it into place. This avoids TOCTOU issues and prevents overwriting a symlink with a regular file.
5. **No authentication.** Tool is for trusted local networks; documented as a known limitation (see §10).
6. **No execution of uploaded files.** The server only serves `GET` (files, directory listing, UI) and `POST` (upload). No `HEAD`/`PUT`/`DELETE`/`OPTIONS`.
7. **Filename sanitization** on upload: the client-visible name is `os.path.basename` of the original name with `NUL` bytes and control characters stripped; the server applies the same rules as a second layer (see §6.3).
8. **Collision policy (upload):** if a file with the same name already exists in the target directory, it is **renamed**: `name.ext` → `name (1).ext` → `name (2).ext` → … (first free index wins). The response reports the final stored name.
9. **No CSRF protection** on upload (consequence of single-origin browser UI + same-host-only binding); documented as limitation.
10. The server sends `Cache-Control: no-store` for the HTML page and listings; files are served with `Content-Length` and `Accept-Ranges: bytes` but **no** byte-range support in v1 (browsers re-GET; see §10).

## 4. HTTP API

Base URL: `http://<address>:<port>/`. All paths below are relative to it.

### 4.1 `GET /`

Serves the single-page UI (`index.html` + embedded CSS/JS as separate strings, concatenated server-side into one response).

- Status **200**, `Content-Type: text/html; charset=utf-8`.
- The HTML contains `<meta name="wm-upload" content="true|false">` and `<meta name="wm-download" content="true|false">` reflecting the CLI flags; the JS reads them to show/hide the upload panel and disable the listing.
- Response body is static per configuration → no per-request cost.

### 4.2 `GET /list?path=<relpath>` — directory listing (requires `--allow-download`)

`<relpath>` is URL-encoded, relative to the base directory. Empty/`/` = base directory.

- **200** → JSON:
  ```json
  {
    "path": "data/test",
    "parent": "data",
    "entries": [
      { "name": "subdir",  "type": "dir",  "size": null, "mtime": null },
      { "name": "file.txt","type": "file", "size": 1234, "mtime": 1727000000 }
    ]
  }
  ```
  - `path`: normalized relative path ("" for base dir, no leading/trailing slash).
  - `parent`: normalized relative path of the parent (only present and non-empty when `path` is non-empty).
  - `entries`: directories first, then files; each group alphabetical, case-insensitive (`key=str.lower`); `.`/`..` never listed (the UI renders `..` itself from `parent`).
  - `size` (int bytes) and `mtime` (unix seconds) only for files; `null` for dirs.
- **403** JSON error — upload/download disabled.
- **404** JSON error — path outside base dir, not a directory, or doesn't exist.
- Symlinked directories inside the base dir: **followed** (they resolve inside), consistent with the file-download rule.

### 4.3 `GET /download?path=<relpath>` — file download (requires `--allow-download`)

- **302** redirect (or **200** with body, both acceptable) to `/file?path=<relpath>`. The UI links directly to `/file?path=...`; `/download` exists so that plain-link usage from e.g. a README still works.
- **403** — disabled. **404** — missing / outside / is a directory.

### 4.4 `GET /file?path=<relpath>` — file contents (requires `--allow-download`)

- **200**, `Content-Type` from `mimetypes.guess_type` (fallback `application/octet-stream`), `Content-Length` set, `Content-Disposition: attachment; filename="<name>"` (RFC 6266 quoting; name = basename, UTF-8).
- Streamed in 1 MiB chunks (no full-file read into memory).
- **403** / **404** as above.

### 4.5 `POST /upload` — upload files (requires `--allow-upload`)

`Content-Type: multipart/form-data`, field name **`files`** (one or more values), plus one required field **`path`** = target sub-directory, relative to base ("" or `/` = base dir).

Behavior:

1. Parse multipart using **FastAPI/Starlette `UploadFile`** objects (parameter type `files: list[UploadFile] = Form(...)`), streaming each file to disk in **1 MiB chunks**. A **request body cap** (default **100 MiB**, see §10) returns **413** when exceeded; enforce it via a middleware that tracks bytes consumed (Starlette's `request.stream()` yields chunks; abort on total > cap).
2. For each `files` entry:
   - Sanitize the original filename as in §3.7; empty result → skip (reported as `"error": "invalid filename"`).
   - Resolve collision name per §3.8 **in the target directory**.
   - Stream to `<targetdir>/.upload-<uuid>.tmp` in **1 MiB chunks**, tracking bytes; final `os.replace(tmp, final)`.
   - On any I/O error mid-file: delete tmp, continue with remaining files, report per-file error.
3. **200** JSON response:
   ```json
   {
     "results": [
       { "original": "a.txt", "stored": "a.txt", "size": 1234, "error": null },
       { "original": "b.txt", "stored": "b (1).txt", "size": 56, "error": null },
       { "original": "", "stored": null, "size": null, "error": "invalid filename" }
     ]
   }
   ```
4. **403** — upload disabled (checked **before** reading the body, to save bandwidth). **400** — bad form-data / missing `path`. **413** — body cap exceeded.
5. Target dir that doesn't exist or resolves outside base dir → per-file `"error": "invalid target"`, HTTP 200 (partial-failure semantics: the batch itself succeeded).
6. `path` values containing NUL → **400**.

### 4.6 Method & path handling

- `HEAD /` → 200, same headers as `GET /`, empty body. Other methods on any path → **405** with `Allow` header. Unknown paths (e.g. `/favicon.ico`) → **404** plain text.

## 5. Client — Single Page

### 5.1 Layout

One HTML document, two stacked sections, both visible:

```
┌────────────────────────────────────────────┐
│  Web File Manager        [address:port]    │   ← header bar
├────────────────────────────────────────────┤
│  Upload panel (hidden if upload disabled)  │
├────────────────────────────────────────────┤
│  Breadcrumb: base › data › test            │
│  ┌────────────────────────────────────────┐│
│  │ ..   12.5 KiB  2026-09-01  file.txt    ││   ← table: name | size | modified
│  │ subdir ▸                                  │
│  └────────────────────────────────────────┘│
└────────────────────────────────────────────┘
```

- Dark-on-light or light-on-dark neutral palette; system font stack; no external fonts/icons. Inline SVG or Unicode glyphs (`▸`, `🗀`-free — use text) for folder/file indicators.
- The listing table has fixed headers (name/size/modified), row hover, right-aligned monospace size column.
- **Breadcrumb** is built client-side from the current `path`: a clickable segment per path component (last segment is plain text). Empty `path` renders only the base-dir name from the `/list` response meta.
- `..` row: present whenever `parent` is non-empty; clicking it loads `parent`.
- Rows are clickable: directories → navigate; files → trigger browser download via `<a href="/file?path=...">` (plain anchor, `download` attribute with basename, so it also works middle-clicked).

### 5.2 Upload dialog (per spec §"Upload interface")

- **Add files**: `<input type="file" multiple>` ("Add files" button). Files appear in a queue as the user adds them — **multiple batches allowed** ("first three files, next another two"): every add appends to the same queue, deduplicated by `(name, size, lastModified)` — re-adding an already-queued identical file is a no-op (no duplicates in the list).
- **Queue list**: one row per queued file: name, human size, and a **per-row remove (✕) button**. The queue is only cleared after a successful upload.
- **Upload button**: enabled when queue is non-empty; disabled while a request is in flight.
- **Progress**: a single overall progress bar (uploaded bytes across the batch / total) + per-file status text (queued → uploading → done ✓ / failed ✗ with the server's error message). `xhr.upload.onprogress` drives it.
- **Target**: the directory currently shown in the file manager (spec: "upload must save to the current directory"). The upload panel shows the current absolute target path as a label; there is no separate target picker in v1 (the file-manager navigation is the target selector).
- On completion the listing is re-fetched and the queue cleared. Per-file failures are listed inline; the dialog stays open.

### 5.3 Feature flags

- `meta[name=wm-upload] = false` → upload panel is removed from the DOM.
- `meta[name=wm-download] = false` → the listing area shows a static notice "Download is disabled on this server" and no `GET /list` request is made; the UI stays on the same page.

## 6. Server Architecture (Python, Uvicorn + FastAPI)

### 6.1 Package layout

```
src/web_file_manager/
  __init__.py        # main() CLI entry (thin: parse args → uvicorn.run())
  config.py          # Config dataclass: base dir, address, port, feature flags
  server.py          # FastAPI app factory: routes, middleware, exception handlers
  paths.py           # containment check, relpath normalize, safe-name sanitize
  static.py          # HTML/CSS/JS strings (template rendered with the two flags)
```

`main()` in `__init__.py` keeps its current signature (it's the `uv` script entry).

### 6.2 Concurrency & startup

- The ASGI app is created once (a `FastAPI` instance) and handed to Uvicorn.
- Handlers are `async`; each request computes its own `realpath` checks (no shared mutable state).
- Startup: `uvicorn.run("web_file_manager.server:app", host=<addr>, port=<port>)`.
- Shutdown: Uvicorn handles `SIGINT`/`SIGTERM` natively (graceful drain), process exits 0.

### 6.3 Path handling (`paths.py`)

- `resolve(rel) -> Path | None`: URL-decode → strip leading `/` → forbid NUL → `realpath(base / rel)` → containment check (§3.1) → return or `None`.
- `safe_filename(name)`: `os.path.basename` → strip NUL/control chars → truncate to 255 bytes (UTF-8, lossy-safe cut at char boundary) → if empty, return `None`.
- `unique_name(dir, name)`: collision loop from §3.8.
- `rel_display(path)`: forward-slash-normalized relative string for API/UI.

### 6.4 Multipart handling (FastAPI/Starlette)

- File uploads arrive as `UploadFile` objects via `files: list[UploadFile] = Form(...)`. Starlette parses the multipart body (backpressure built-in, streaming to spooled files ≤ 1 MB in memory, then to tmp).
- `path` arrives as `path: str = Form(...)`. Missing/empty → 400 (FastAPI validation → 422 is remapped by the exception handler to 400 for the upload endpoint).
- Body cap (413) is enforced by a middleware that reads `request.stream()` in 1 MiB chunks and raises if the total exceeds the cap.

### 6.5 Response conventions

- Errors are raised as `fastapi.HTTPException(status_code, detail)` and answered by a registered exception handler as JSON `{"error": "<short message>"}` (except 404 on unknown **URL paths** — plain text "Not Found" — and 405).
- JSON: `ensure_ascii=False`, `Content-Type: application/json; charset=utf-8` (Starlette default JSON response, with the `no-store` header set by middleware).
- Every response includes `Cache-Control: no-store` except `/file` (default). Set via a `@app.middleware("http")` pass-through.
- Method & path: FastAPI/Starlette return 405 (with `Allow`) for wrong methods and 404 for unmatched paths out of the box; the only special-case is `HEAD /` → 200 empty body (handled by an explicit `HEAD` route).

## 7. Acceptance Scenarios (manual; no tests in scope)

Run with `uv run web-file-manager -d <dir> [--allow-upload] [--allow-download] [-a -p]`:

1. **Defaults**: `uv run web-file-manager` → serves on `localhost:8080`, base dir = cwd, both features off → `GET /` 200 (UI shows both notices), `GET /list` 403, `POST /upload` 403.
2. **Download only**: `--allow-download` on a dir with subdirs and files → browser walks `..`/dir links, breadcrumb correct, clicking a file downloads it with the right name/extension; `GET /file?path=../etc/passwd` → 404; symlink to outside base dir → 404.
3. **Upload only**: `--allow-upload` → UI listing shows the disabled-notice; upload dialog works: add 3 files, add 2 more (queue of 5, no duplicates), remove one (queue 4), upload → all land in the **currently displayed** directory; re-upload same name → `(1)` suffix; 110 MiB single file → 413.
4. **Both flags**: upload from `/list`-navigated subdir saves into that subdir (server-side verified with `ls`); refresh listing shows the new file with correct size.
5. **CLI errors**: non-existent `-d` → exit 2 with message; `-p 0` / `-p 99999` → argparse error, exit 2.
6. **Signals**: `Ctrl+C` during a request → clean "Shutting down...", exit 0.

## 8. Non-Goals (v1)

- Authentication / TLS / multi-user.
- Byte-range requests, resumable uploads, upload progress above a single overall bar.
- Create/rename/delete directories or files; recursive upload of directories (browser `webkitdirectory` not used).
- File editing in the browser, thumbnails, previews.
- i18n beyond English UI strings; custom CSS themes.
- Any server dependency other than Uvicorn + FastAPI (i.e. no gunicorn, no custom ASGI servers); any frontend build step or CDN asset.

## 9. Dependencies & Tooling

- **Runtime** (Python ≥ 3.12 per `pyproject.toml`):
  - `uvicorn[standard]` — ASGI server.
  - `fastapi` — web framework (routing, parameter parsing, responses, middleware).
- Dev loop: `uv run web-file-manager ...`; packaging unchanged (`uv_build`, script entry `web-file-manager = "web_file_manager:main"` already wired).
- `uv.lock` pins the two runtime packages; any future addition must be justified in a spec revision.

## 10. Known Limitations (accepted)

| # | Limitation | Rationale |
|---|---|---|
| 1 | No auth | Out of scope; bind to `localhost` by default. Documented in README. |
| 2 | Single overall upload progress bar | Simpler than per-file XHR pooling; spec requires "uploading progress", one bar satisfies it. |
| 3 | No byte ranges on download | v1; large files still stream fine, just no `Range` support. |
| 4 | 100 MiB per-request upload cap | Protects process memory (each in-flight file costs 1 tmp-file on disk, parser buffer ≤ 1 MiB). |
| 5 | Symlinks inside base dir are followed for reading | Standard `realpath`-containing semantics; symlinks pointing outside are blocked. |
| 6 | Uploads spooled by Starlette (`UploadFile`) | Built-in multipart handling (backpressure, spooling to tmp after 1 MB); body cap still enforced by middleware (413). |
