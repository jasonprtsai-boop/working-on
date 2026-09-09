#!/usr/bin/env python3
"""Send a safe fake trigger to a TMflow Listen node.

This script sends only variable assignments and `ScriptExit()` through the TM
Listen Node protocol. It does not send motion or IO commands. The purpose is to
release Listen1 so the existing TMflow graph can run one cycle.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from dataclasses import dataclass


DEFAULT_ROBOT_IP = "192.168.10.10"
DEFAULT_SOURCE_IP = "192.168.10.50"
DEFAULT_PORT = 5890


@dataclass(frozen=True)
class TMPacket:
    header: str
    data: str
    checksum: str
    raw: bytes


def xor_checksum(content: bytes) -> int:
    value = 0
    for byte in content:
        value ^= byte
    return value


def build_packet(header: str, data: str) -> bytes:
    data_bytes = data.encode("utf-8")
    body = header.encode("ascii") + b"," + str(len(data_bytes)).encode("ascii")
    body += b"," + data_bytes + b","
    checksum = f"{xor_checksum(body):02X}".encode("ascii")
    return b"$" + body + b"*" + checksum + b"\r\n"


def parse_packet(raw: bytes) -> TMPacket:
    if not raw.startswith(b"$") or not raw.endswith(b"\r\n"):
        raise ValueError(f"invalid packet framing: {raw!r}")
    star_index = raw.rfind(b"*")
    if star_index < 0:
        raise ValueError(f"packet missing checksum separator: {raw!r}")
    body = raw[1:star_index]
    received = raw[star_index + 1 : -2].decode("ascii", errors="strict")
    expected = f"{xor_checksum(body):02X}"
    if received.upper() != expected:
        raise ValueError(f"checksum mismatch: received={received}, expected={expected}")
    first_comma = body.find(b",")
    second_comma = body.find(b",", first_comma + 1)
    if first_comma < 0 or second_comma < 0 or not body.endswith(b","):
        raise ValueError(f"invalid packet fields: {raw!r}")
    header = body[:first_comma].decode("ascii")
    declared_length = int(body[first_comma + 1 : second_comma])
    data_bytes = body[second_comma + 1 : -1]
    if len(data_bytes) != declared_length:
        raise ValueError(f"length mismatch: declared={declared_length}, actual={len(data_bytes)}")
    return TMPacket(header=header, data=data_bytes.decode("utf-8", errors="replace"), checksum=received.upper(), raw=raw)


def receive_packets(sock: socket.socket, timeout: float) -> list[TMPacket]:
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    packets: list[TMPacket] = []
    while time.monotonic() < deadline:
        sock.settimeout(max(0.05, deadline - time.monotonic()))
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buffer.extend(chunk)
        while b"\r\n" in buffer:
            end = buffer.index(b"\r\n") + 2
            raw = bytes(buffer[:end])
            del buffer[:end]
            packets.append(parse_packet(raw))
    return packets


def listen_is_active(packets: list[TMPacket]) -> bool | None:
    status_packets = [packet for packet in packets if packet.header == "TMSTA" and packet.data.startswith("00,")]
    if not status_packets:
        return None
    fields = status_packets[-1].data.split(",", 2)
    if len(fields) < 2:
        return None
    return fields[1].strip().lower() == "true"


def normalize_source_ip(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"auto", "none"}:
        return None
    return text


def connect_socket(
    robot_ip: str,
    source_ip: str | None,
    port: int,
    timeout: float,
    wait_seconds: float,
) -> socket.socket:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    last_error: OSError | None = None

    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            if source_ip:
                sock.bind((source_ip, 0))
            sock.connect((robot_ip, port))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            if time.monotonic() >= deadline:
                raise last_error
            time.sleep(0.5)


def receive_and_print(sock: socket.socket, timeout: float) -> None:
    for packet in receive_packets(sock, timeout=timeout):
        print(f"[RX] {packet.header}: {packet.data}")


def send_script_line(sock: socket.socket, line_id: int, script: str, timeout: float) -> None:
    packet = build_packet("TMSCT", f"{line_id},{script}")
    print(f"[TX] {packet.decode('utf-8').rstrip()}")
    sock.sendall(packet)
    receive_and_print(sock, timeout=min(0.5, timeout))


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely release a TMflow Listen node once.")
    parser.add_argument("--robot-ip", default=DEFAULT_ROBOT_IP)
    parser.add_argument("--source-ip", default=DEFAULT_SOURCE_IP, help='Use "auto" to let Windows choose.')
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="Keep retrying until Listen opens.")
    parser.add_argument("--from-index", type=int, help="Set var_active_from before releasing Listen1.")
    parser.add_argument("--to-index", type=int, help="Set var_active_to before releasing Listen1.")
    parser.add_argument("--action", type=int, choices=(0, 1), help="Set var_active_action: 0=normal move, 1=capture.")
    parser.add_argument("--cmd-id", type=int, default=1, help="Set var_active_cmd_id when command fields are provided.")
    parser.add_argument("--skip-listen-check", action="store_true", help="Send ScriptExit without checking TMSTA 00 first.")
    args = parser.parse_args()

    robot_ip = str(args.robot_ip)
    source_ip = normalize_source_ip(args.source_ip)
    port = int(args.port)
    timeout = float(args.timeout)
    wait_seconds = float(args.wait_seconds)

    command_fields = [args.from_index, args.to_index, args.action]
    set_command = any(value is not None for value in command_fields)
    if set_command and not all(value is not None for value in command_fields):
        print("[FAIL] --from-index, --to-index and --action must be provided together.")
        return 1

    print("TMflow fake trigger")
    print(f"Robot endpoint : {robot_ip}:{port}")
    print(f"Source IP      : {source_ip or 'Windows auto'}")
    if set_command:
        print(f"Command        : from={args.from_index}, to={args.to_index}, action={args.action}, cmd_id={args.cmd_id}")
    else:
        print("Command        : none, ScriptExit() only")
    if wait_seconds > 0:
        print(f"Wait           : up to {wait_seconds:g} seconds for Listen to open")

    sock: socket.socket | None = None
    try:
        sock = connect_socket(robot_ip, source_ip, port, timeout, wait_seconds)
        print("[OK] TCP connected")

        receive_and_print(sock, timeout=0.3)

        if not args.skip_listen_check:
            query = build_packet("TMSTA", "00")
            sock.sendall(query)
            packets = receive_packets(sock, timeout=timeout)
            for packet in packets:
                print(f"[RX] {packet.header}: {packet.data}")
            active = listen_is_active(packets)
            if active is not True:
                print("[STOP] TMflow is not inside Listen node yet. Start the project and wait at Listen1 first.")
                return 1

        line_id = 1
        if set_command:
            send_script_line(sock, line_id, f"var_active_from={args.from_index}", timeout)
            line_id += 1
            send_script_line(sock, line_id, f"var_active_to={args.to_index}", timeout)
            line_id += 1
            send_script_line(sock, line_id, f"var_active_action={args.action}", timeout)
            line_id += 1
            send_script_line(sock, line_id, f"var_active_cmd_id={args.cmd_id}", timeout)
            line_id += 1

        send_script_line(sock, line_id, "ScriptExit()", timeout)
        print("[DONE] Fake trigger sent. TMflow should leave Listen1 through Pass and run one cycle.")
        return 0
    except OSError as exc:
        print(f"[FAIL] TCP error: {exc}")
        return 2
    except ValueError as exc:
        print(f"[FAIL] Packet parse error: {exc}")
        return 3
    finally:
        if sock is not None:
            sock.close()


if __name__ == "__main__":
    sys.exit(main())
