#!/usr/bin/env python3
"""Start only the PC-side Modbus server used by TMflow square commands.

This is a commissioning helper. It does not start vision, the chess engine, or
automatic robot execution. Keep it running while configuring TMflow's Modbus
Device, then stop it with Ctrl+C when the connection test is complete.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

print("[BOOT] Loading SMART Chess Modbus server helper...", flush=True)

from backend.infrastructure.robot.modbus_adapter import ModbusAdapter
from backend.utils import config

try:
    from pyModbusTCP.client import ModbusClient
except ImportError:
    ModbusClient = None


def say(message: str = "") -> None:
    print(message, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the PC Modbus TCP server for TMflow 1.82 square-command tests."
    )
    parser.add_argument("--host", default=str(getattr(config, "ROBOT_MODBUS_SERVER_HOST", "192.168.10.50")))
    parser.add_argument("--port", type=int, default=int(getattr(config, "ROBOT_MODBUS_SERVER_PORT", 502)))
    parser.add_argument("--robot-ip", default=str(getattr(config, "ROBOT_IP", "192.168.10.10")))
    parser.add_argument("--pc-ip", default=str(getattr(config, "ROBOT_PC_IP", "192.168.10.50")))
    parser.add_argument("--subnet-mask", default=str(getattr(config, "ROBOT_SUBNET_MASK", "255.255.0.0")))
    parser.add_argument("--duration", type=float, default=0.0, help="Seconds to run; 0 means until Ctrl+C.")
    parser.add_argument("--watch", action="store_true", help="Print command/status registers when values change.")
    parser.add_argument("--watch-interval", type=float, default=1.0)
    parser.add_argument(
        "--test-move",
        default="",
        help="Optional UCCI move such as a0b1. The helper writes one test command after startup.",
    )
    parser.add_argument("--test-capture", action="store_true", help="Send the optional test move as action_type=1.")
    parser.add_argument("--test-delay", type=float, default=3.0, help="Seconds to wait before sending --test-move.")
    parser.add_argument("--test-timeout", type=float, default=15.0, help="Seconds to wait for TMflow completion.")
    return parser.parse_args()


def apply_modbus_server_config(args: argparse.Namespace) -> None:
    config.FAKE_ROBOT = False
    config.AUTO_EXECUTE_ROBOT = False
    config.ROBOT_ADAPTER = "modbus"
    config.ROBOT_IP = str(args.robot_ip).strip()
    config.ROBOT_PC_IP = str(args.pc_ip).strip()
    config.ROBOT_SUBNET_MASK = str(args.subnet_mask).strip()
    config.ROBOT_PORT = 502
    config.ROBOT_MODBUS_ROLE = "server"
    config.ROBOT_MODBUS_SERVER_HOST = str(args.host).strip()
    config.ROBOT_MODBUS_SERVER_PORT = int(args.port)
    config.ROBOT_MODBUS_PAYLOAD_MODE = "square_command"
    config.ROBOT_MODBUS_REGISTER_ADDRESSING = "holding_40001"


def print_connection_plan(args: argparse.Namespace) -> None:
    say("\n=== PC Network ===")
    say(f"PC Ethernet IP      : {args.pc_ip}")
    say(f"PC subnet mask      : {args.subnet_mask}")
    say(f"TM Robot IP         : {args.robot_ip}")
    say("TM Robot subnet mask: 255.255.0.0")

    say("\n=== Python Modbus Server ===")
    say("Run on PC:")
    say(
        "  .\\.venv\\Scripts\\python.exe scripts\\start_modbus_square_server.py "
        f"--host {args.host} --port {args.port} --watch"
    )
    say(f"Listen endpoint     : {args.host}:{args.port}")
    say("AUTO_EXECUTE_ROBOT  : false")

    say("\n=== TMflow 1.82 Input ===")
    say("Use node/function   : Modbus Device")
    say("Do NOT use          : Listen node")
    say("Required role check : ModbusDev must be an external Modbus TCP device/client, not only Robot Slave Mapping")
    say(f"Device IP           : {args.host}")
    say(f"Device port         : {args.port}")
    say("Unit/Slave ID       : 1")
    say("Signal type         : 16-bit Holding Register; use the equivalent name shown by this TMflow build")
    say("Address display     : confirm whether UI address 400001 maps to protocol offset 0")
    say("Compatibility       : Python mirrors command words to input registers for builds that expose RI-style reads")
    say("Start address       : 0")
    say("TMflow operation    : use Modbus Device Read/Write nodes with source/destination variables")

    say("\n=== Register Map ===")
    for line in register_lines():
        say(line)
    say("")


def register_lines() -> Iterable[str]:
    return (
        "address 0  -> TMflow reads  from_square",
        "address 1  -> TMflow reads  to_square",
        "address 2  -> TMflow reads  action_type",
        "address 3  -> TMflow reads  cmd_id",
        "address 4  -> TMflow reads  trigger",
        "address 5  <- TMflow writes status (0 idle, 1 busy, 2 done, 3 error, 4 controller fault)",
        "address 6  <- TMflow writes error_code",
        "address 7  <- TMflow writes completed_cmd_id",
        "address 8  <- TMflow writes heartbeat",
        "address 9  <- TMflow writes robot_state",
    )


def self_test_tcp(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=2.0):
            return True
    except OSError as exc:
        say(f"[FAIL] Local TCP self-test failed: {exc}")
        return False


def self_test_modbus_protocol(host: str, port: int) -> bool:
    if ModbusClient is None:
        say("[WARN] Modbus protocol self-test skipped: pyModbusTCP client unavailable.")
        return True
    client = ModbusClient(host=str(host), port=int(port), auto_open=True, timeout=2.0)
    test_address = 1000
    test_value = 12345
    try:
        if not client.write_single_register(test_address, test_value):
            say(f"[FAIL] Modbus protocol self-test write failed at address {test_address}.")
            return False
        values = client.read_holding_registers(test_address, 1)
        if values != [test_value]:
            say(f"[FAIL] Modbus protocol self-test readback failed: {values!r}")
            return False
        client.write_single_register(test_address, 0)
        say("[OK] Local Modbus protocol self-test succeeded.")
        return True
    except Exception as exc:
        say(f"[FAIL] Local Modbus protocol self-test failed: {exc}")
        return False
    finally:
        try:
            client.close()
        except Exception:
            pass


def read_registers(adapter: ModbusAdapter) -> list[int | None]:
    registers = [
        config.ROBOT_SQUARE_FROM_REGISTER,
        config.ROBOT_SQUARE_TO_REGISTER,
        config.ROBOT_SQUARE_ACTION_REGISTER,
        config.ROBOT_SQUARE_COMMAND_ID_REGISTER,
        config.ROBOT_SQUARE_TRIGGER_REGISTER,
        config.ROBOT_SQUARE_STATUS_REGISTER,
        config.ROBOT_SQUARE_ERROR_CODE_REGISTER,
        config.ROBOT_SQUARE_COMPLETED_COMMAND_REGISTER,
        config.ROBOT_SQUARE_HEARTBEAT_REGISTER,
        config.ROBOT_SQUARE_ROBOT_STATE_REGISTER,
    ]
    return [adapter._read_register(register) for register in registers]


def print_register_snapshot(values: list[int | None]) -> None:
    names = [
        "from",
        "to",
        "action",
        "cmd_id",
        "trigger",
        "status",
        "error",
        "completed",
        "heartbeat",
        "robot_state",
    ]
    pairs = " ".join(f"{name}={value}" for name, value in zip(names, values))
    say(f"[REG] {pairs}")


def start_test_move_thread(adapter: ModbusAdapter, args: argparse.Namespace) -> None:
    move = str(args.test_move).strip()
    if not move:
        return

    def worker() -> None:
        delay = max(0.0, float(args.test_delay))
        say(f"[TEST] Will send test move {move} after {delay:.1f}s.")
        time.sleep(delay)
        say(f"[TEST] Sending test move {move}; capture={bool(args.test_capture)}")
        ok = adapter.send_chess_move(
            move,
            is_capture=bool(args.test_capture),
            timeout=float(args.test_timeout),
        )
        if ok:
            say(f"[TEST] Test move {move} completed.")
        else:
            say(f"[TEST] Test move {move} failed: {adapter.last_error}")

    thread = threading.Thread(target=worker, name="modbus-test-move", daemon=True)
    thread.start()


def main() -> int:
    args = parse_args()
    apply_modbus_server_config(args)
    print_connection_plan(args)

    adapter = ModbusAdapter(host=config.ROBOT_IP, port=config.ROBOT_PORT)
    if not adapter.connect():
        say(f"[FAIL] Could not start Modbus server: {adapter.last_error}")
        say("Check that the PC owns the host IP and that the port is not already in use.")
        return 2

    say("[OK] Python Modbus server started.")
    if self_test_tcp(config.ROBOT_MODBUS_SERVER_HOST, config.ROBOT_MODBUS_SERVER_PORT):
        say("[OK] Local TCP self-test succeeded.")
    else:
        adapter.disconnect()
        return 3
    if not self_test_modbus_protocol(config.ROBOT_MODBUS_SERVER_HOST, config.ROBOT_MODBUS_SERVER_PORT):
        adapter.disconnect()
        return 4

    say("Keep this window open while TMflow tests Modbus Device. Press Ctrl+C to stop.")
    start_test_move_thread(adapter, args)

    deadline = None if args.duration <= 0 else time.monotonic() + float(args.duration)
    previous = None
    try:
        while deadline is None or time.monotonic() < deadline:
            if args.watch:
                values = read_registers(adapter)
                if values != previous:
                    print_register_snapshot(values)
                    previous = values
            time.sleep(max(0.05, float(args.watch_interval)))
    except KeyboardInterrupt:
        say("\nStopping Modbus server.")
    finally:
        adapter.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
