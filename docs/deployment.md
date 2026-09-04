# Deployment & Operations

This is a **single-process, local-first** tool. It is designed to be run directly
(`uv run web-file-manager`) rather than packaged as a system service, but the notes
below cover running it longer-term and hardening the deployment.

## Trust model (read first)

- **No authentication** (accepted limitation, spec §10). Anyone who can reach the
  port can browse/download/upload within the base dir.
- **Default bind is `localhost`** — by default only the local machine can reach it.
- For anything non-local, you **must** add auth (reverse proxy, firewall, TLS
  termination) and keep the base dir to files you're willing to expose.

## Running

```sh
# explicit flags
uv run web-file-manager -d /srv/shared --allow-upload --allow-download -a 0.0.0.0 -p 8443
```

- `-a 0.0.0.0` binds all interfaces (only do this behind a trusted interface / proxy).
- The process logs the startup banner to **stderr** (INFO) and blocks until a
  signal. Request logs and warnings also go to stderr — point your log collector
  there (see [Logging](#logging)).

## Logging

All logs (banner, per-request lines, warnings, errors) are written to **stderr**
via the stdlib `logging` module at INFO level, formatted
`YYYY-MM-DD HH:MM:SS,ms LEVEL logger: message`. There is no file handler and no
rotating log — collect stderr from the process (or via a supervisor) and ship it
wherever you keep logs.

- **Per request** (one `INFO` line): `GET /list?path=... -> 200 (127.0.0.1, 1.2ms)`.
- **`WARNING`** lines mark the notable events: over-cap bodies (413), rejected
  uploads (400), failed file writes, and *path-traversal attempts* (`resolve`
  escaping the base dir — worth investigating in a shared deployment).
- **`ERROR` + traceback** appears only if an unhandled exception leaks out of a
  request (the server is designed to keep serving, so treat this as a bug report).

To keep request logs out of a low-noise stream while retaining the warnings, raise
the level of just the request logger at the process-manager level (or set the
`WEB_FILE_MANAGER_LOG_LEVEL` if you add one — there is none today); today the whole
stream is one level (INFO).

## Signals & shutdown

- `SIGINT`/`SIGTERM` → Uvicorn drains in-flight requests, prints `Shutting down...`,
  and exits **0**.
- Start-stop via `Ctrl+C`, `kill <pid>`, or a process manager (see below).

## Process supervision (optional)

If you want it to auto-restart or run as a long-lived service, wrap the **same
command** — the app itself is a single process:

**systemd** (example):

```ini
[Unit]
Description=Web File Manager
After=network.target

[Service]
WorkingDirectory=/path/to/web-file-manager
ExecStart=/path/to/web-file-manager/.venv/bin/python -m web_file_manager \
    -d /srv/shared --allow-download --allow-upload -a 127.0.0.1 -p 8080
Restart=on-failure
User=wfm

[Install]
WantedBy=multi-user.target
```

**Supervisor / runit / Docker** work the same way: run
`python -m web_file_manager <flags>` as the foreground process; it blocks until a
signal, so no special "wait" logic is needed.

## Scaling

- The service is **single-process by design** (spec §1). For higher concurrency or
  availability, run multiple instances behind a reverse proxy / load balancer
  (each instance is independent and stateless — config is per-process).
- A reverse proxy is the natural place to add TLS, auth, and rate limiting. Example
  with nginx (TLS + auth) in front of the app on `127.0.0.1:8080`:

  ```nginx
  server {
      listen 443 ssl;
      # ... ssl_certificate ...
      location / {
          proxy_pass http://127.0.0.1:8080;
          proxy_set_header Host $host;
          client_max_body_size 105m;   # just above the 100 MiB app cap
      }
  }
  ```

## Operational notes

- **Log**: everything goes to **stderr** (timestamped, INFO level) — banner,
  per-request lines, warnings, errors. See [Logging](#logging) above. Point a
  process manager / log collector at the process's stderr.
- **Disk**: uploads need write access to the target dir; the per-file temp file
  (`.upload-<uuid>.tmp`) is created in the *target* directory and `os.replace`d into
  place. Ensure the run user can write there.
- **Temp files**: Starlette spool temps + the upload temp files are cleaned up on
  completion or error. If the process is hard-killed mid-upload, a stray
  `.upload-*.tmp` may remain; it is inert (hidden, `os.replace`d only on success).
- **100 MiB body cap**: over-cap uploads are rejected (413) before parsing. If you
  raise the cap (spec revision), also raise any reverse-proxy `client_max_body_size`.
- **No state to back up or migrate** — there is no database; the served tree *is*
  the data.

## Verification after deploy

```sh
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/                      # 200
curl -s localhost:8080/list | head                                            # JSON
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8080/file?path=../x"      # 404 (containment)
```
