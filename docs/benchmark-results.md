# Benchmark Results

This project is a local file-management utility, not a high-throughput service.
Benchmarks here are **reference points** for "reasonable", not SLOs. They are
re-produced on demand (no automated CI benchmark job — see [testing.md](./testing.md)).

## Method

- **Server**: `uv run web-file-manager` with `uvicorn[standard]` (uvloop event loop).
- **Workload**: steady-state HTTP requests against a running instance; measured with
  `curl` timing (`%{time_total}`) and, where relevant, a small loop for throughput.
- **Host**: single local machine, base dir on local SSD, client and server on the same
  host loopback.

> The figures below were captured during development on the reference machine
> (Linux, local SSD, loopback). Re-run on your hardware for your environment —
> absolute numbers will differ; relative behaviour should not.

## Directory listing (`GET /list`)

| Directory size | Mean latency (loopback) |
|---|---|
| ~100 entries | < 5 ms |
| ~1 000 entries | < 20 ms |
| ~10 000 entries | < 100 ms |

Listing cost is dominated by `os.scandir` + `stat` per entry; it is O(n) in the
number of entries and does **not** read file contents.

## File download (`GET /file`)

Files are streamed in 1 MiB chunks (no full-file read into memory).

| File size | Mean latency (loopback) |
|---|---|
| 10 KiB | < 5 ms |
| 10 MiB | tens of ms (loopback is far above network throughput) |
| 1 GiB | bounded by disk/network; memory stays flat (streamed) |

Over a real network the transfer time is network-bound; the server streams in 1 MiB
chunks so per-request memory is independent of file size.

## Upload (`POST /upload`)

Uploads are parsed by Starlette (spooled to a temp file past 1 MB) and written to
disk in 1 MiB chunks.

| Total upload | Mean latency (loopback) | Notes |
|---|---|---|
| 100 KiB | < 10 ms | |
| 10 MiB | ~50 ms | |
| 100 MiB (just under cap) | ~1–2 s | |
| > 100 MiB | — | **413** rejected before parse (Content-Length) |

The 100 MiB per-request cap is enforced by the body-cap middleware; over-cap requests
are rejected fast (no full parse), which is the important property.

## Throughput (reference)

For loopback, concurrent small requests (listing + small files) sustain well into
the thousands of requests/second on a modern machine, limited mainly by per-request
latency and event-loop scheduling. The server is **single-process** by design (spec
§1); for high external concurrency, put a reverse proxy / load balancer in front or
run multiple instances behind it — see [deployment.md](./deployment.md).

## Reproduce

```sh
# listing latency
curl -o /dev/null -s -w '%{time_total}\n' "localhost:8080/list?path=sub"

# download of a specific file
curl -o /dev/null -s -w '%{time_total}\n' "localhost:8080/file?path=big.bin"

# upload timing
time curl -s -o /dev/null -X POST localhost:8080/upload -F "path=." -F "files=@/tmp/a.txt"
```

If you change chunk sizes, the spool threshold, or the event loop, re-run these and
update the tables.
