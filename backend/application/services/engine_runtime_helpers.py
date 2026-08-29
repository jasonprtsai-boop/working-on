import asyncio
import queue
from typing import Dict, Optional


def new_output_queue(max_size: int) -> "queue.Queue[str]":
    return queue.Queue(maxsize=max(1, int(max_size)))


def drain_output_queue(output_queue: "queue.Queue[str]") -> None:
    while not output_queue.empty():
        try:
            output_queue.get_nowait()
        except queue.Empty:
            break


def enqueue_output_line(output_queue: "queue.Queue[str]", line: str, *, logger=None) -> None:
    try:
        output_queue.put_nowait(line)
        return
    except queue.Full:
        try:
            output_queue.get_nowait()
        except queue.Empty:
            pass

    try:
        output_queue.put_nowait(line)
    except queue.Full:
        if logger:
            logger.debug("[EngineService] output queue full; dropped latest engine line")


async def get_output_line(output_queue: "queue.Queue[str]", timeout: float = 1.0) -> str:
    deadline = asyncio.get_running_loop().time() + max(0.0, float(timeout))
    while True:
        try:
            return output_queue.get_nowait()
        except queue.Empty:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise
            await asyncio.sleep(min(0.05, remaining))


def build_engine_diagnostics_payload(
    *,
    status: str,
    error: Optional[str],
    active_nnue_path: Optional[str],
    compatibility_status: str,
) -> Dict[str, Dict[str, Optional[str]]]:
    return {
        "engine": {
            "status": status,
            "error": error,
            "active_nnue_path": active_nnue_path,
            "compatibility_status": compatibility_status,
        }
    }
