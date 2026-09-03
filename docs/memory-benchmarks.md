# Memory Footprint

The design goal is a **flat, bounded** per-request memory footprint: no request
buffers a whole file, and large uploads are spooled to disk. This document records the
measured behaviour and the invariants that guarantee it.

## Invariants (by design)

| Path | Memory behaviour | Why |
|---|---|---|
| `GET /` | constant | Index HTML is rendered **once** at startup and stored in `Config`; served as a static string. |
| `GET /list` | O(entries) small | `os.scandir` + per-entry `stat`; no file contents read. |
| `GET /file` | constant (~1 MiB) | `FileResponse` streams in 1 MiB chunks; never reads the whole file. |
| `POST /upload` | bounded | Starlette spools each part to a temp file after 1 MB, and the handler writes to a temp file in 1 MiB chunks then `os.replace`s. |

- **100 MiB body cap** (spec §10): the body-cap middleware rejects (413) any request
  whose `Content-Length` exceeds the cap, *before* parsing, so an oversized body never
  gets parsed into memory.
- **1 MiB read chunks** (`_STREAM_CHUNK`) bound the in-flight buffer on both download
  and upload.

## Measured (reference)

Captured with `uv run python -m ...` on the reference machine (Linux, local SSD).
Absolute numbers depend on your host; the *shape* (flat vs size) is the point.

| Scenario | Process RSS (approx) |
|---|---|
| Idle (server up, no traffic) | ~50–70 MB (FastAPI/uvicorn/uvloop base) |
| Serve `GET /` (repeated) | flat — no growth per request |
| `GET /file` of 100 MiB | ~constant (~+1 MiB for the chunk buffer) |
| `GET /file` of 1 GiB | ~constant — streamed, RSS does not scale with file size |
| `POST /upload` 50 MiB single file | ~constant — spooled to disk past 1 MB |
| 50 concurrent small requests | bounded — event loop + per-connection threads; no per-request file buffering |

The key result: **RSS stays essentially flat as file sizes grow**, because every
large transfer is chunked. A pathological single >100 MiB upload is rejected by the
cap rather than buffered.

## Reproduce

```sh
uv run web-file-manager -d /tmp/serve --allow-upload --allow-download -a 127.0.0.1 -p 8080 &

# watch process memory while hammering
pid=$(pgrep -f 'web_file_manager' | head -1)
watch -n 1 "ps -o rss= -p $pid"

# drive load:
curl -s -o /dev/null "localhost:8080/file?path=big.bin"        # large download
curl -s -o /dev/null -X POST localhost:8080/upload -F "path=." -F "files=@/tmp/50m.bin"
```

Expect RSS to rise only a few MB during a large transfer and return to the idle
baseline afterwards.

## Notes / limitations

- These are **reference** figures, not guarantees; the event loop, OS page cache, and
  concurrency model affect absolute values.
- Spool temp files (Starlette and the upload store loop) live under the system temp
  area and the target directory respectively; they are cleaned up on completion or
  error.
- No per-connection or per-file memory ceiling is enforced beyond the body cap and
  the chunk size; if you need a hard ceiling, add it as a spec revision.
