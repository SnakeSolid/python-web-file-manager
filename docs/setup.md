# Development Setup

This guide covers getting the project running locally.

## Prerequisites

- **Python ≥ 3.12** (`requires-python` in `pyproject.toml`).
- **`uv`** — the project's package/environment manager. The project uses the
  `uv_build` build backend and a `uv.lock`-pinned dependency set.

## Install & run

```sh
# 1. Install runtime dependencies into the project venv (fastapi, uvicorn,
#    python-multipart — see pyproject.toml).
uv sync

# 2. Run the file manager (console script wired by pyproject [project.scripts]).
uv run web-file-manager -d /path/to/serve --allow-upload --allow-download
```

Equivalent module form (both are entry points to the same `main()`):

```sh
uv run web-file-manager ...
uv run python -m web_file_manager ...
```

The process blocks until `SIGINT`/`SIGTERM`, then prints `Shutting down...` and
exits 0 (Uvicorn handles signal draining).

## CLI flags

| Flag(s) | Dest | Default | Description |
|---|---|---|---|
| `--address`, `-a` | `address` | `localhost` | Bind address (host name or IP). |
| `--port`, `-p` | `port` | `8080` | TCP port (1–65535, argparse-enforced). |
| `--base-dir`, `-d` | `base_dir` | `.` | Directory to expose, resolved to an absolute path. |
| `--allow-upload` | `allow_upload` | `false` | Enable the upload endpoint. |
| `--allow-download` | `allow_download` | `false` | Enable listing / download. |

### Startup validation & exit codes

- **Exit 2** — `--base-dir` does not exist or is not a directory
  (`error: base directory '<path>' does not exist or is not a directory`).
- **Exit 2** — port out of range (`-p 0`, `-p 99999`, `-p abc`) — argparse error.
- **Exit 2** — the address cannot be bound (`Address already in use`, unknown
  host). Both an up-front probe and a catch around `uvicorn.run` enforce this.
- **Exit 0** — normal shutdown on `SIGINT`/`SIGTERM`.

A startup banner is printed to stdout (see [architecture.md](./architecture.md)).

## Why the dependencies exist

| Dependency | Role |
|---|---|
| `fastapi` | Routing, `Form`/`UploadFile` multipart parsing, responses, middleware, exception handlers. |
| `uvicorn[standard]` | ASGI server (HTTP/1.1 + uvloop event loop). |
| `python-multipart` | Required by Starlette/FastAPI to parse `multipart/form-data` bodies. |

These are the **only** runtime dependencies. Adding more requires a spec revision
(spec §9).

## Debugging tips

- Run with the default `log_level="warning"`; Uvicorn/ASGI tracebacks go to stderr
  and are timestamped by `logging.basicConfig` in the package `__init__`.
- The server never crashes on a bad request: unhandled request errors are caught and
  answered (4xx/5xx) while the process keeps serving.
- For a quick smoke test of the API without a browser:

  ```sh
  uv run web-file-manager -d /tmp/serve --allow-upload --allow-download &
  curl -s localhost:8080/list
  curl -s -X POST localhost:8080/upload -F "path=." -F "files=@/tmp/a.txt"
  ```

## Layout

See [architecture.md](./architecture.md) for the package structure and how each
module fits together.
