from __future__ import annotations

import socket
import time
from typing import Any

from backend.infrastructure.robot.tmflow_json_protocol import (
    FINAL_STATUSES,
    RobotCommand,
    RobotResponse,
    TMflowJsonProtocolError,
    parse_json_line,
)


class TMflowJsonClient:
    """Blocking TCP client for TMflow newline-delimited JSON messages."""

    def __init__(self, host: str, port: int, *, timeout: float = 3.0, max_message_bytes: int = 4096):
        self.host = str(host)
        self.port = int(port)
        self.timeout = float(timeout)
        self.max_message_bytes = int(max_message_bytes)
        self.sock: socket.socket | None = None

    @property
    def connected(self) -> bool:
        return self.sock is not None

    def connect(self) -> None:
        self.close()
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        if not sock:
            return
        try:
            sock.close()
        except OSError:
            pass

    def send(self, command: RobotCommand, *, wire_format: str = "envelope") -> None:
        if not self.sock:
            raise ConnectionError("TMflow JSON client is not connected.")
        self.sock.sendall(command.to_json_line(wire_format=wire_format))

    def read_message(self, *, timeout: float | None = None) -> dict[str, Any]:
        if not self.sock:
            raise ConnectionError("TMflow JSON client is not connected.")
        read_timeout = float(timeout if timeout is not None else self.timeout)
        deadline = time.monotonic() + read_timeout
        buffer = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out reading TMflow JSON response.")
            self.sock.settimeout(max(0.001, remaining))
            try:
                chunk = self.sock.recv(1)
            except socket.timeout as exc:
                raise TimeoutError("Timed out reading TMflow JSON response.") from exc
            if not chunk:
                raise ConnectionError("TMflow socket closed.")
            if chunk == b"\n":
                break
            buffer.extend(chunk)
            if len(buffer) > self.max_message_bytes:
                raise TMflowJsonProtocolError("TMflow JSON response exceeds maximum message size.")
        return parse_json_line(bytes(buffer))

    def transact(
        self,
        command: RobotCommand,
        *,
        wire_format: str = "envelope",
        ack_timeout: float = 2.0,
        done_timeout: float = 30.0,
        expect_ack: bool = False,
    ) -> RobotResponse:
        self.send(command, wire_format=wire_format)

        if expect_ack:
            first = self._read_matching_response(command.id, timeout=ack_timeout)
            if first.status == "ACK":
                return self._wait_for_final(command.id, timeout=done_timeout)
            if first.status in FINAL_STATUSES:
                if first.status == "DONE":
                    raise TMflowJsonProtocolError(f"TMflow command {command.id} completed without ACK.")
                return first
            raise TMflowJsonProtocolError(f"Expected ACK for {command.id}, got {first.raw!r}.")

        return self._wait_for_final(command.id, timeout=done_timeout)

    def _wait_for_final(self, command_id: str, *, timeout: float) -> RobotResponse:
        deadline = time.monotonic() + float(timeout)
        last_response: RobotResponse | None = None
        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            response = self._read_matching_response(command_id, timeout=remaining)
            last_response = response
            if response.is_final:
                return response
        raise TimeoutError(f"Timed out waiting for TMflow DONE/ERROR for {command_id}; last={last_response!r}")

    def _read_matching_response(self, command_id: str, *, timeout: float) -> RobotResponse:
        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            response = RobotResponse.from_mapping(self.read_message(timeout=remaining))
            if response.id == command_id:
                return response
        raise TimeoutError(f"Timed out waiting for TMflow response id {command_id}.")
