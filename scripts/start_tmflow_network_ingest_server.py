#!/usr/bin/env python3
"""Run only the PC-side TMflow Network Node ingest server.

This helper is intentionally narrower than `backend.main`: it opens the same
TMflow socket ingest path used by the application, but it does not initialize
robot motion, Modbus, vision workers, or the web UI.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state
from backend.infrastructure.robot.tmflow_socket_ingest_server import TMflowSocketIngestServer
from backend.utils import config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the TMflow Network Node TCP ingest server only.")
    parser.add_argument("--host", default=getattr(config, "TMFLOW_INGEST_SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(getattr(config, "TMFLOW_INGEST_SERVER_PORT", 9001)))
    parser.add_argument("--watch-interval", type=float, default=0.2)
    parser.add_argument("--no-ack", action="store_true", help="Do not send ACK/ERR lines back to TMflow.")
    parser.add_argument("--key", default=None, help="Optional ingest key. Leave empty for lab CSV tests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = TMflowSocketIngestServer(
        host=str(args.host),
        port=int(args.port),
        send_ack=not bool(args.no_ack),
        ingest_key=args.key,
    )
    if not server.start():
        print(f"[FAIL] TMflow ingest server failed to listen on {args.host}:{args.port}: {server.last_error}", flush=True)
        return 1

    print("[OK] TMflow Network ingest server started.", flush=True)
    print(f"Listen endpoint : {args.host}:{args.port}", flush=True)
    print("TMflow Device   : ntd_PC_TCP", flush=True)
    print("TMflow target   : PC IP 192.168.10.50, port 9001", flush=True)
    print(r'First test send : "HB,1\n"', flush=True)
    print(r"Supported CSV   : HB,1\n | BUSY,42 | DONE,42 | ERR,42,900", flush=True)
    print("Keep this window open while TMflow runs. Press Ctrl+C to stop.", flush=True)

    last = {
        "connections": -1,
        "messages_received": -1,
        "parse_failures": -1,
        "auth_failures": -1,
        "last_remote": "",
        "last_bad_message": "",
        "summary": "",
    }
    try:
        while True:
            status = server.get_status()
            snapshot = tmflow_ingest_state.snapshot()
            summary = _snapshot_summary(snapshot)
            current = {
                "connections": status.get("connections", 0),
                "messages_received": status.get("messages_received", 0),
                "parse_failures": status.get("parse_failures", 0),
                "auth_failures": status.get("auth_failures", 0),
                "last_remote": status.get("last_remote") or "",
                "last_bad_message": status.get("last_bad_message") or "",
                "summary": summary,
            }
            if current != last:
                delta_connections = _delta(current["connections"], last["connections"])
                delta_messages = _delta(current["messages_received"], last["messages_received"])
                delta_parse_failures = _delta(current["parse_failures"], last["parse_failures"])
                delta_auth_failures = _delta(current["auth_failures"], last["auth_failures"])
                print(
                    "[INGEST] "
                    f"connections={current['connections']}{_delta_text(delta_connections)} "
                    f"messages={current['messages_received']}{_delta_text(delta_messages)} "
                    f"parse_failures={current['parse_failures']}{_delta_text(delta_parse_failures)} "
                    f"auth_failures={current['auth_failures']}{_delta_text(delta_auth_failures)} "
                    f"remote={current['last_remote'] or '-'} "
                    f"{_raw_bad_text(current['last_bad_message'])}"
                    f"{summary}",
                    flush=True,
                )
                last = current
            time.sleep(max(0.05, float(args.watch_interval)))
    except KeyboardInterrupt:
        print("\nStopping TMflow Network ingest server.", flush=True)
    finally:
        server.stop()
    return 0


def _delta(current: int, previous: int) -> int:
    if previous < 0:
        return 0
    return int(current) - int(previous)


def _delta_text(delta: int) -> str:
    if delta > 0:
        return f"(+{delta})"
    if delta < 0:
        return f"({delta})"
    return ""


def _raw_bad_text(raw_bad: str) -> str:
    return f"raw_bad={raw_bad} " if raw_bad else ""


def _snapshot_summary(snapshot: dict) -> str:
    if not snapshot:
        return "state=waiting"
    parts = []
    if snapshot.get("heartbeat_seen"):
        parts.append("heartbeat=seen")
    if snapshot.get("robot_state_label"):
        parts.append(f"robot_state={snapshot['robot_state_label']}")
    if snapshot.get("status_label"):
        parts.append(f"status={snapshot['status_label']}")
    if snapshot.get("completed_command_id") is not None:
        parts.append(f"completed={snapshot['completed_command_id']}")
    if snapshot.get("current_command_id") is not None:
        parts.append(f"cmd={snapshot['current_command_id']}")
    if snapshot.get("error_code") is not None:
        parts.append(f"error={snapshot['error_code']}")
    pose_text = _pose_summary(snapshot)
    if pose_text:
        parts.append(f"pose={pose_text}")
    if snapshot.get("raw"):
        parts.append(f"raw={snapshot['raw']}")
    return " ".join(parts) if parts else "state=updated"


def _pose_summary(snapshot: dict) -> str:
    telemetry = snapshot.get("telemetry") if isinstance(snapshot.get("telemetry"), dict) else {}
    tcp = telemetry.get("tcp") if isinstance(telemetry.get("tcp"), list) else None
    if tcp and len(tcp) >= 6:
        return ",".join(_format_number(value) for value in tcp[:6])
    position = snapshot.get("position") if isinstance(snapshot.get("position"), dict) else {}
    orientation = snapshot.get("orientation") if isinstance(snapshot.get("orientation"), dict) else {}
    keys = ("x", "y", "z", "rx", "ry", "rz")
    values = [
        position.get("x"),
        position.get("y"),
        position.get("z"),
        orientation.get("rx"),
        orientation.get("ry"),
        orientation.get("rz"),
    ]
    if all(value is not None for value in values):
        return ",".join(_format_number(value) for value in values)
    return ""


def _format_number(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
