import http.client
import sys

HOST = "127.0.0.1"
PORT = 8170
BOUNDARY = "----wfmcheck7d3f"


def upload(path_field: str, files: list[tuple[str, bytes]]) -> tuple[int, str]:
    body = b""
    if path_field:
        body += (
            f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="path"\r\n\r\n'
            f"{path_field}\r\n".encode()
        )
    for name, data in files:
        body += (
            (
                f"--{BOUNDARY}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n".encode()
            )
            + data
            + b"\r\n"
        )
    body += f"--{BOUNDARY}--\r\n".encode()
    print(
        f"  [req] path={path_field!r} files={len(files)} bodylen={len(body)}",
        flush=True,
    )
    conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
    conn.request(
        "POST",
        "/upload",
        body=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
            "Content-Length": str(len(body)),
            "Connection": "close",
        },
    )
    print("  [req] request sent, awaiting response...", flush=True)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    print(f"  [resp] {resp.status}", flush=True)
    return resp.status, raw.decode()


def show(title, path_field, files):
    print(f"== {title}", flush=True)
    try:
        status, raw = upload(path_field, files)
    except Exception as e:
        print(f"   EXCEPTION: {e!r}", flush=True)
        return
    print(f"  {status}\n  {raw}", flush=True)
    return status, raw


# 1) upload new file to base
show("upload new (base)", "", [("up1.txt", b"first\n")])
# 2) upload collision -> unique name
show("upload collision", "", [("up1.txt", b"second\n")])
# 3) upload into subdir via path field
show("upload to subdir", "sub", [("inner2.txt", b"deep\n")])
# 4) bad target dir -> per-file invalid target
show("bad target dir", "doesnotexist", [("x.txt", b"zzz\n")])
# 5) NUL in path -> 400
show("NUL path", "a\x00b", [("x.txt", b"zzz\n")])
