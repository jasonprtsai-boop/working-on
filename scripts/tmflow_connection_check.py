#!/usr/bin/env python3
"""Safely diagnose Python <-> TMflow Listen Node communication.

This script never sends a robot motion command.  It only:
1. opens TCP port 5890;
2. asks TMflow whether the flow is currently inside a Listen Node (TMSTA 00);
3. validates and prints the returned packet.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from dataclasses import dataclass


DEFAULT_ROBOT_IP = "192.168.10.10"
# Keep this aligned with ROBOT_PC_IP in the lab setup docs.
DEFAULT_SOURCE_IP = "192.168.10.50"
DEFAULT_PORT = 5890


@dataclass(frozen=True)
class TMPacket:
    header: str
    data: str
    checksum: str
    raw: bytes


def xor_checksum(content: bytes) -> int:
    """Return the XOR of all bytes between '$' and '*'."""
    value = 0
    for byte in content:
        value ^= byte
    return value


def build_packet(header: str, data: str) -> bytes:
    """Build a TM protocol packet using UTF-8 byte length."""
    data_bytes = data.encode("utf-8")
    body = header.encode("ascii") + b"," + str(len(data_bytes)).encode("ascii")
    body += b"," + data_bytes + b","
    checksum = f"{xor_checksum(body):02X}".encode("ascii")
    return b"$" + body + b"*" + checksum + b"\r\n"


def parse_packet(raw: bytes) -> TMPacket:
    """Parse and validate one complete TM packet."""
    if not raw.startswith(b"$") or not raw.endswith(b"\r\n"):
        raise ValueError(f"封包起訖格式錯誤：{raw!r}")

    star_index = raw.rfind(b"*")
    if star_index < 0:
        raise ValueError(f"封包缺少 * 校驗碼分隔符：{raw!r}")

    body = raw[1:star_index]
    received_checksum = raw[star_index + 1 : -2].decode("ascii", errors="strict")
    expected_checksum = f"{xor_checksum(body):02X}"
    if received_checksum.upper() != expected_checksum:
        raise ValueError(
            f"XOR 校驗碼錯誤：收到 {received_checksum}，應為 {expected_checksum}"
        )

    first_comma = body.find(b",")
    second_comma = body.find(b",", first_comma + 1)
    if first_comma < 0 or second_comma < 0 or not body.endswith(b","):
        raise ValueError(f"封包欄位格式錯誤：{raw!r}")

    header = body[:first_comma].decode("ascii")
    declared_length = int(body[first_comma + 1 : second_comma])
    data_bytes = body[second_comma + 1 : -1]
    if len(data_bytes) != declared_length:
        raise ValueError(
            f"資料長度錯誤：宣告 {declared_length} bytes，實際 {len(data_bytes)} bytes"
        )

    return TMPacket(
        header=header,
        data=data_bytes.decode("utf-8", errors="replace"),
        checksum=received_checksum.upper(),
        raw=raw,
    )


def receive_packets(sock: socket.socket, timeout: float) -> list[TMPacket]:
    """Receive all complete CRLF-terminated packets until timeout."""
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


def explain_socket_error(exc: OSError) -> str:
    winerror = getattr(exc, "winerror", None)
    if winerror == 10061:
        return "目標主機拒絕連線：TMflow 的 5890 Listener 尚未啟動。"
    if winerror == 10060 or isinstance(exc, TimeoutError):
        return "連線逾時：請檢查路由、防火牆或機器人端 Listener。"
    if winerror == 10049:
        return "來源 IP 無效：192.168.10.50 未設定在目前電腦的網卡上。"
    return f"Socket 錯誤：{exc}"


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


def diagnose(
    robot_ip: str,
    source_ip: str | None,
    port: int,
    timeout: float,
    wait_seconds: float,
) -> int:
    print("TMflow 連線診斷（不會移動機械手臂）")
    print(f"機器人：{robot_ip}:{port}")
    print(f"來源 IP：{source_ip or '由 Windows 自動選擇'}")
    if wait_seconds > 0:
        print(f"等待 Listen 開啟：最多 {wait_seconds:g} 秒")

    sock: socket.socket | None = None
    try:
        sock = connect_socket(robot_ip, source_ip, port, timeout, wait_seconds)
    except OSError as exc:
        print("\n[失敗] TCP 5890 無法連線")
        print(explain_socket_error(exc))
        print("\nTMflow 端請確認：")
        print("1. 專案內確實有 Listen Node。")
        print("2. 專案已儲存並按下執行，不只是開啟編輯畫面。")
        print("3. Notice Log 已顯示 TCPListener 的 IP 與 Port 5890。")
        print("4. 停止專案、重新執行；仍失敗再重新啟動控制器。")
        return 2

    try:
        local_ip, local_port = sock.getsockname()
        print(f"\n[成功] TCP 已連線，本機端點：{local_ip}:{local_port}")

        # A flow already inside Listen may immediately send a TMSCT entry message.
        initial_packets = receive_packets(sock, timeout=0.5)
        for packet in initial_packets:
            print(f"[機器人主動訊息] {packet.header}: {packet.data}")

        query = build_packet("TMSTA", "00")
        print(f"[送出] {query.decode('utf-8').rstrip()}")
        sock.sendall(query)

        packets = receive_packets(sock, timeout=timeout)
        if not packets:
            print("\n[異常] TCP 已連線，但 TMflow 沒有回覆 TMSTA 00。")
            print("請查看 TMflow Notice Log 是否出現封包或校驗錯誤。")
            return 3

        for packet in packets:
            print(f"[收到] {packet.raw.decode('utf-8', errors='replace').rstrip()}")

        status_packets = [
            packet
            for packet in packets
            if packet.header == "TMSTA" and packet.data.startswith("00,")
        ]
        if not status_packets:
            print("\n[異常] 收到資料，但沒有 TMSTA 00 狀態回覆。")
            return 4

        fields = status_packets[-1].data.split(",", 2)
        in_listen = len(fields) >= 2 and fields[1].strip().lower() == "true"
        listen_message = fields[2] if len(fields) >= 3 else ""

        if in_listen:
            print("\n[完成] TMflow 已進入 Listen Node，可開始傳送 TMSCT 指令。")
            if listen_message:
                print(f"Listen 訊息：{listen_message}")
            return 0

        print("\n[部分成功] Python 與 5890 通訊正常，但流程尚未進入 Listen Node。")
        print("請讓 TMflow 的執行標記走到 Listen Node，再執行本程式。")
        return 1
    except (OSError, ValueError) as exc:
        print(f"\n[異常] 通訊或封包解析失敗：{exc}")
        return 5
    finally:
        if sock is not None:
            sock.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安全檢查 Python 與 TMflow Listen Node（Port 5890）"
    )
    parser.add_argument("--robot-ip", default=DEFAULT_ROBOT_IP)
    parser.add_argument(
        "--source-ip",
        default=DEFAULT_SOURCE_IP,
        help='強制使用乙太網路來源 IP；傳入 "auto" 可由 Windows 自動選擇',
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="等待 Listen 開啟並重試連線")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return diagnose(
        robot_ip=args.robot_ip,
        source_ip=normalize_source_ip(args.source_ip),
        port=args.port,
        timeout=args.timeout,
        wait_seconds=args.wait_seconds,
    )


if __name__ == "__main__":
    sys.exit(main())
