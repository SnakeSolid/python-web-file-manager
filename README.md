# Web File Manager

A single-process Python web service that exposes a directory tree as a browser-based
file manager. Users can walk the tree and download files; optionally they can upload
files into any visible directory. Self-contained — no external services, no database,
no client-side network dependencies.

Built with **FastAPI** + **Uvicorn** (ASGI). The client is a single self-contained
HTML/CSS/vanilla-JS page (no CDN, no build step, no external assets).

- **Build/manager**: `uv` (the project uses `uv` + `uv_build`).
- **Runtime deps**: `fastapi`, `uvicorn[standard]`, `python-multipart` (see
  [`docs/setup.md`](./docs/setup.md) for why each is present).

## Quick start

```sh
uv sync                      # install runtime deps (fastapi, uvicorn, python-multipart)
uv run web-file-manager -d /path/to/serve --allow-upload --allow-download
```

The server listens on `localhost:8080` by default. See [Development](#development)
for the full flag list.

> **Trust model**: there is **no authentication** (§[Security](#security) in
> `docs/architecture.md`). Bind to `localhost` (the default) or a trusted interface.
> This is documented as an accepted limitation.

## Development

The full developer guide (setup, running, flags, debugging) is in
[`docs/setup.md`](./docs/setup.md). In short:

```sh
uv run web-file-manager [-a ADDRESS] [-p PORT] [-d BASE_DIR]
                        [--allow-upload] [--allow-download]
```

- `-a/--address` — bind address (default `localhost`)
- `-p/--port` — TCP port, 1–65535 (default `8080`)
- `-d/--base-dir` — directory to expose, resolved to an absolute path (default `.`)
- `--allow-upload` — enable `POST /upload` (default off)
- `--allow-download` — enable listing/download (default off)

With both flags off the server still starts (it returns 403/404 for file operations)
and logs a warning to stderr.

## Documentation

| Topic | Document |
|-------|----------|
| Development setup | [docs/setup.md](./docs/setup.md) |
| Architecture & design | [docs/architecture.md](./docs/architecture.md) |
| Coding conventions | [docs/coding-standards.md](./docs/coding-standards.md) |
| Testing strategy | [docs/testing.md](./docs/testing.md) |
| Benchmarks | [docs/benchmark-results.md](./docs/benchmark-results.md) |
| Memory footprint | [docs/memory-benchmarks.md](./docs/memory-benchmarks.md) |
| Deployment & operations | [docs/deployment.md](./docs/deployment.md) |
| Functional specification | [docs/specification.md](./docs/specification.md) |

## License
 
This project is licensed under the [MIT License](LICENSE).
