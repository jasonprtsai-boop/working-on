#!/usr/bin/env python3
"""Tiny TCP server for checking whether TMflow can connect to the PC.

This deliberately avoids Modbus. Use it with a TMflow Network node to verify the
basic robot -> PC TCP path before debugging Modbus Device settings.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start a plain TCP probe server for TMflow network tests.")
    parser.add_argument("--host", default="192.168.10.50")
    parser.add_argument("--port", type=int, default=9000)
    return parser.parse_args()


def handle_client(conn: socket.socket, addr) -> None:
    print(f"[TCP] connected from {addr}", flush=True)
    try:
        conn.sendall(b"PC_READY\n")
        while True:
            data = conn.recv(4096)
            if not data:
                break
            text = data.decode("utf-8", errors="replace").strip()
            print(f"[TCP] recv from {addr}: {text!r}", flush=True)
            conn.sendall(b"ACK\n")
    except OSError as exc:
        print(f"[TCP] client error {addr}: {exc}", flush=True)
    finally:
        try:
            conn.close()
        except OSError:
            pass
        print(f"[TCP] disconnected {addr}", flush=True)


def main() -> int:
    args = parse_args()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((str(args.host), int(args.port)))
        sock.listen()
        print(f"[OK] TCP probe server listening on {args.host}:{args.port}", flush=True)
        print("Keep this window open. Press Ctrl+C to stop.", flush=True)
        try:
            while True:
                conn, addr = sock.accept()
                thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                thread.start()
        except KeyboardInterrupt:
            print("\nStopping TCP probe server.", flush=True)
            time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
