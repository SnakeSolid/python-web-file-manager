"""web_file_manager — a single-process web file manager (FastAPI + Uvicorn).

Entry point for the ``web-file-manager`` console script (see ``pyproject.toml``) and
``python -m web_file_manager``. ``main()`` parses the CLI, validates the base
directory, builds the FastAPI app, and hands it to Uvicorn.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from pathlib import Path

import uvicorn

from .config import Config
from .server import create_app
from .static import render_index

__all__ = ["main"]

# Unhandled request errors are logged to stderr with a timestamp.
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s"
)


def _port(value: str) -> int:
    """argparse type: port must be in 1..65535."""
    try:
        port = int(value)
    except ValueError:
        port = -1
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"invalid port: {value!r} (must be 1-65535)")
    return port


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web-file-manager",
        description="Expose a directory tree as a browser-based file manager.",
    )
    _ = parser.add_argument(
        "-a",
        "--address",
        default="localhost",
        help="bind address (host name or IP); default: localhost",
    )
    _ = parser.add_argument(
        "-p",
        "--port",
        type=_port,
        default=8080,
        help="TCP port (1-65535); default: 8080",
    )
    _ = parser.add_argument(
        "-d",
        "--base-dir",
        default=".",
        help="directory to expose, resolved to an absolute path; default: current dir",
    )
    _ = parser.add_argument(
        "--allow-upload",
        action="store_true",
        help="enable the upload endpoint",
    )
    _ = parser.add_argument(
        "--allow-download",
        action="store_true",
        help="enable directory listing and file download",
    )
    return parser


def _resolve_base_dir(value: str) -> Path:
    """Resolve ``value`` to an absolute path and validate it is a directory.

    Exits with status 2 (and a message) when it does not exist or is not a
    directory, per spec §2.
    """
    abs_path = Path(os.path.abspath(os.path.expanduser(value)))
    if not abs_path.is_dir():
        print(
            f"error: base directory '{abs_path}' does not exist or is not a directory",
            file=sys.stderr,
        )
        sys.exit(2)
    return abs_path


def main() -> None:
    args = _build_parser().parse_args()

    base_dir = _resolve_base_dir(args.base_dir)
    index_html = render_index(args.allow_upload, args.allow_download)
    config = Config(
        base_dir=base_dir,
        allow_upload=args.allow_upload,
        allow_download=args.allow_download,
        index_html=index_html,
    )

    # Startup banner (spec §2).
    print(f"Web file manager: http://{args.address}:{args.port}/")
    print(f"Base directory: {config.base_dir}")
    print(f"Upload enabled: {'yes' if args.allow_upload else 'no'}")
    print(f"Download enabled: {'yes' if args.allow_download else 'no'}")
    if not args.allow_upload and not args.allow_download:
        print(
            "warning: both upload and download are disabled; "
            "the server will return 403/404 for all file operations",
            file=sys.stderr,
        )

    # Verify the address is bindable up front; a bind failure exits 2 (spec §2).
    _check_bind(args.address, args.port)

    # Run Uvicorn directly on the built app. Uvicorn handles SIGINT/SIGTERM
    # natively (graceful drain, exit 0). A bind failure that slips past the
    # probe (e.g. the address resolves to something unbindable) still exits 2.
    app = create_app(config)
    try:
        uvicorn.run(app, host=args.address, port=args.port, log_level="warning")
    except OSError as e:
        print(f"error: cannot bind to {args.address}:{args.port}: {e}", file=sys.stderr)
        sys.exit(2)


def _check_bind(address: str, port: int) -> None:
    """Fail fast (exit 2) if the address:port cannot be bound."""
    try:
        info = socket.getaddrinfo(
            address, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
        )
    except socket.gaierror as e:
        print(f"error: cannot bind: {e}", file=sys.stderr)
        sys.exit(2)
    proto, _, _, _, sockaddr = info[0]
    with socket.socket(proto, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(sockaddr)
        except OSError as e:
            print(f"error: cannot bind to {address}:{port}: {e}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
