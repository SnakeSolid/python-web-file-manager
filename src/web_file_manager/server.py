"""FastAPI application for the web file manager.

``create_app(config)`` builds the ASGI app (routes, middleware, exception handlers);
``main()`` in :mod:`web_file_manager` builds it and hands the instance straight to
Uvicorn. FastAPI/Starlette objects do the heavy lifting: routing, ``Form``/
``UploadFile`` multipart parsing, ``FileResponse``/``RedirectResponse``/
``HTMLResponse``, middleware, and exception handlers. The only hand-rolled pieces
are the body-cap middleware (413) and the per-file upload store loop.
"""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)

from .config import Config
from .paths import rel_display, resolve, safe_filename, unique_name

__all__ = ["create_app"]

# 100 MiB per-request upload cap (spec §10).
_BODY_CAP = 100 * 1024 * 1024
# Stream upload bodies to disk in 1 MiB chunks (spec §4.5).
_STREAM_CHUNK = 1024 * 1024


def create_app(config: Config) -> FastAPI:
    """Build the FastAPI app for the given (immutable) configuration."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config

    # ------------------------------------------------------------ middleware

    @app.middleware("http")
    async def _no_store(request: Request, call_next):
        # Every response carries ``Cache-Control: no-store`` except ``/file``
        # (spec §6.5).
        response = await call_next(request)
        if request.url.path != "/file":
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.middleware("http")
    async def _body_cap(request: Request, call_next):
        # Enforce the per-request body cap (413) *before* the body is parsed
        # (spec §4.5 / §6.4). Uses Content-Length when present. A Response is
        # returned directly (not an exception) because BaseHTTPMiddleware does
        # not translate raised exceptions into responses.
        if request.method == "POST":
            raw_len = request.headers.get("content-length")
            if raw_len:
                try:
                    length = int(raw_len)
                except ValueError:
                    length = 0
                if length > _BODY_CAP:
                    return Response(
                        status_code=413,
                        content=json.dumps({"error": "request body too large"}),
                        media_type="application/json; charset=utf-8",
                        headers={"Cache-Control": "no-store"},
                    )
        return await call_next(request)

    # ------------------------------------------------------- exception handlers

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        # All JSON errors are answered as ``{"error": "<message>"}`` (spec §6.5).
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail or ""},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Remap 422 (bad/missing form-data) to 400 for the upload endpoint (spec §6.4).
        return JSONResponse(
            status_code=400,
            content={"error": "invalid form data"},
        )

    # ------------------------------------------------------------------- routes

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        # GET -> full UI; HEAD -> 200 with the same headers, empty body (spec §4.6).
        if request.method == "HEAD":
            return HTMLResponse(config.index_html, headers={"Content-Length": "0"})
        return HTMLResponse(config.index_html)

    @app.get("/list")
    async def list_dir(path: str = ""):
        if not config.allow_download:
            raise HTTPException(403, "download is disabled")
        resolved = resolve(config.base_dir, path)
        if resolved is None or not resolved.is_dir():
            raise HTTPException(404, "not found")

        entries: list[dict[str, Any]] = []
        try:
            with os.scandir(resolved) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir(follow_symlinks=True)
                    except OSError:
                        continue
                    if is_dir:
                        entries.append(
                            {
                                "name": entry.name,
                                "type": "dir",
                                "mime": None,
                                "size": None,
                                "mtime": None,
                            }
                        )
                    else:
                        st = entry.stat(follow_symlinks=True)
                        # MIME type drives the UI's icon class and matches the
                        # Content-Type /file will serve (None if unknown).
                        ctype, _ = mimetypes.guess_type(entry.name)
                        entries.append(
                            {
                                "name": entry.name,
                                "type": "file",
                                "mime": ctype,
                                "size": st.st_size,
                                "mtime": int(st.st_mtime),
                            }
                        )
        except OSError:
            raise HTTPException(404, "not found")

        entries.sort(key=lambda e: e["name"].lower())
        dirs = [e for e in entries if e["type"] == "dir"]
        files = [e for e in entries if e["type"] == "file"]

        rel = rel_display(resolved, config.base_dir)
        # ``parent`` is the display name of the directory being listed (used by
        # the client as the breadcrumb's base label). Empty at the base dir.
        parent = os.path.basename(rel) if rel else ""
        return {"path": rel, "parent": parent, "entries": dirs + files}

    @app.get("/download")
    async def download(path: str = ""):
        if not config.allow_download:
            raise HTTPException(403, "download is disabled")
        resolved = resolve(config.base_dir, path)
        if resolved is None or not resolved.is_file():
            raise HTTPException(404, "not found")
        # 302 redirect to the canonical /file endpoint (spec §4.3).
        return RedirectResponse(f"/file?path={path}", status_code=302)

    @app.get("/file")
    async def file(path: str = ""):
        if not config.allow_download:
            raise HTTPException(403, "download is disabled")
        resolved = resolve(config.base_dir, path)
        if resolved is None or not resolved.is_file():
            raise HTTPException(404, "not found")
        ctype, _ = mimetypes.guess_type(resolved.name)
        ctype = ctype or "application/octet-stream"
        # FileResponse sets Content-Length, streams in chunks; we add the
        # attachment disposition and Accept-Ranges (spec §4.4 / §3.10).
        return FileResponse(
            resolved,
            media_type=ctype,
            filename=resolved.name,
            headers={"Accept-Ranges": "bytes"},
        )

    @app.post("/upload")
    async def upload(
        path: str = Form(""),
        files: list[UploadFile] = Form(...),  # noqa: B008
    ):
        # 403 when disabled, checked before reading the body (saves bandwidth).
        if not config.allow_upload:
            raise HTTPException(403, "upload is disabled")
        if "\x00" in path:
            raise HTTPException(400, "path contains NUL")

        # Second-layer cap for chunked bodies (no Content-Length): the total
        # file size must stay under the request-body cap. Spooled UploadFiles
        # cost little memory, so we guard by total size rather than buffering.
        if sum(f.size or 0 for f in files) > _BODY_CAP:
            raise HTTPException(413, "request body too large")

        target_dir = resolve(config.base_dir, path)
        if target_dir is None or not target_dir.is_dir():
            target_dir = None  # per-file "invalid target"

        results: list[dict[str, Any]] = []
        for upload_file in files:
            results.append(await _store_upload_file(upload_file, target_dir))

        if not results:
            raise HTTPException(400, "no files provided")
        return {"results": results}

    return app


async def _store_upload_file(
    upload_file: UploadFile, target_dir: Path | None
) -> dict[str, Any]:
    """Stream one uploaded file to disk in 1 MiB chunks; return its record.

    Writes to a temp file in the target directory and ``os.replace``s it into
    place, so a symlink is never followed or overwritten (spec §3.4).
    """
    original = upload_file.filename or ""
    safe = safe_filename(original)
    if safe is None:
        return {
            "original": original,
            "stored": None,
            "size": None,
            "error": "invalid filename",
        }
    if target_dir is None:
        # Consume the body so the connection stays in sync, then report.
        await upload_file.seek(0)
        while await upload_file.read(_STREAM_CHUNK):
            pass  # drain the spooled body
        return {
            "original": original,
            "stored": None,
            "size": None,
            "error": "invalid target",
        }

    final = unique_name(target_dir, safe)
    tmp = target_dir / f".upload-{uuid.uuid4().hex}.tmp"
    size = 0
    try:
        with tmp.open("wb") as out:
            while True:
                chunk = await upload_file.read(_STREAM_CHUNK)
                if not chunk:
                    break
                _ = out.write(chunk)
                size += len(chunk)
        os.replace(tmp, final)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "original": original,
            "stored": None,
            "size": None,
            "error": "write failed",
        }
    return {
        "original": original,
        "stored": final.name,
        "size": size,
        "error": None,
    }
