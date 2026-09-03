# Testing Strategy

**Automated tests are explicitly out of scope for this project** (spec §7: "no
tests in scope"). There is no test suite, no CI test job, and no `pytest`
configuration. Validation is **manual acceptance** per the scenarios in
[specification.md §7](./specification.md#7-acceptance-scenarios-manual-no-tests-in-scope).

This document records *how* to verify the server manually, so a change can be
checked without an automated suite.

## How to run

Start the server, then drive it with `curl` (no browser required):

```sh
uv run web-file-manager -d /tmp/serve --allow-upload --allow-download -a 127.0.0.1 -p 8080 &
```

Wait for the startup banner, then probe:

```sh
curl -s localhost:8080/                                   # 200, HTML with meta flags
curl -s localhost:8080/list                              # 200 JSON listing
curl -s "localhost:8080/list?path=sub"                  # 200 JSON (parent set)
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8080/file?path=../etc/passwd"  # 404
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8080/download?path=a.txt"        # 302
curl -s -D - -o /dev/null "localhost:8080/file?path=a.txt"   # headers: disposition/length
curl -s -X POST localhost:8080/upload -F "path=." -F "files=@/tmp/a.txt"            # 200 results
```

## Manual acceptance checklist (from spec §7)

1. **Defaults** — no flags: `GET /` 200 (UI shows both disabled notices),
   `GET /list` 403, `POST /upload` 403.
2. **Download only** (`--allow-download`) — walk `..`/dirs via `/list`, breadcrumb
   correct, file download keeps name/extension; `file?path=../etc/passwd` → 404;
   symlink pointing outside the base dir → 404.
3. **Upload only** (`--allow-upload`) — upload to the *current* directory works;
   re-upload same name → `(1)` suffix; a 101 MiB single file → **413**.
4. **Both flags** — upload from a navigated subdir saves into that subdir
   (verify with `ls`); a refetched listing shows the new file with the right size.
5. **CLI errors** — non-existent `-d` → exit 2 + message; `-p 0` / `-p 99999` →
   argparse error, exit 2.
6. **Signals** — `Ctrl+C` during a request → clean `Shutting down...`, exit 0.

## What *is* checked automatically (build-time only)

- `uv run python -m compileall src/web_file_manager/` — byte-compiles the package
  (catches syntax errors). This is a build sanity check, not a behaviour test.
- `uv sync` resolves the pinned dependency set from `uv.lock`.

## Regression notes

When you change behaviour, re-run the relevant item(s) above manually. Because
there is no suite, pay extra attention to:

- The upload path (multipart parsing, collision rename, per-file errors, 413 cap).
- Path containment (traversal, symlinks, NUL, absolute paths).
- Flag gating (403s must come **before** the body is read for uploads).

If a change is large enough that manual coverage feels inadequate, the right move is
to raise it as a spec revision (to add tests) rather than silently adding a test
framework that the spec excludes.
