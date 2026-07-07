import asyncio
import hashlib
import os
import queue
import shutil
import tempfile
import time
from contextlib import suppress
from typing import Dict, List, Optional

from backend.events.bus.event_bus import bus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.core.engine_parser import EngineParser
from backend.utils import config
from backend.utils.logger import logger


class EngineService:
    """
    Async UCI engine controller with startup probing.

    Behavior:
    - Build a candidate NNUE list once.
    - Probe candidates and lock the first compatible pair.
    - Expose probe status so health checks can report a clear result.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = os.path.abspath(path or config.ENGINE_PATH)
        self.configured_nnue_candidates = self._build_candidate_list()
        self.active_nnue_path: Optional[str] = None

        self.process = None
        self.reader_task = None
        self.running = False
        self.output_queue: "queue.Queue[str]" = queue.Queue(maxsize=max(1, int(config.ENGINE_OUTPUT_QUEUE_SIZE)))

        self.last_internal_error: Optional[str] = None
        self.last_startup_error: Optional[str] = None
        self.compatibility_status = "unprobed"
        self.compatibility_report: List[Dict[str, object]] = []
        self._probe_task: Optional[asyncio.Task] = None
        self._probing_candidate = False
        self._compute_lock: Optional[asyncio.Lock] = None
        self._compute_lock_loop = None
        self._closing = False
        self._shutdown_requested = False

    def _build_candidate_list(self) -> List[str]:
        candidates: List[str] = []
        for raw_path in getattr(config, "ENGINE_NNUE_CANDIDATES", []):
            abs_path = os.path.abspath(raw_path)
            if abs_path not in candidates:
                candidates.append(abs_path)
        return candidates

    def _resolve_nnue_path(self, source_path: str) -> str:
        """
        Mirror non-ASCII paths to an ASCII-safe temp directory for Windows subprocesses.
        """
        if not source_path or not os.path.exists(source_path):
            return source_path

        try:
            source_path.encode("ascii")
            return source_path
        except UnicodeEncodeError:
            pass

        safe_dir = os.path.join(tempfile.gettempdir(), "smart-chess-engine")
        os.makedirs(safe_dir, exist_ok=True)
        source_hash = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:10]
        file_name = os.path.basename(source_path)
        name, ext = os.path.splitext(file_name)
        safe_path = os.path.join(safe_dir, f"{name}-{source_hash}{ext}")
        try:
            if not os.path.exists(safe_path) or os.path.getmtime(safe_path) < os.path.getmtime(source_path):
                shutil.copy2(source_path, safe_path)
            logger.info(f"[EngineService] using ASCII-safe NNUE path: {safe_path}")
            return safe_path
        except Exception:
            logger.warning("[EngineService] failed to mirror NNUE file; using original path", exc_info=True)
            return source_path

    def get_probe_status(self) -> Dict[str, object]:
        return {
            "status": self.compatibility_status,
            "engine_path": self.path,
            "active_nnue_path": self.active_nnue_path,
            "candidates": list(self.configured_nnue_candidates),
            "report": list(self.compatibility_report),
            "last_startup_error": self.last_startup_error,
        }

    def schedule_probe(self):
        """
        Fire-and-forget startup probe. Safe to call multiple times.
        """
        if self._shutdown_requested:
            return None
        if self._probe_task and not self._probe_task.done():
            return self._probe_task
        self._probe_task = asyncio.create_task(self.probe_compatible_pair())
        return self._probe_task

    async def probe_compatible_pair(self, force: bool = False) -> bool:
        if self._shutdown_requested:
            self.compatibility_status = "shutdown"
            return False
        if self.compatibility_status == "matched" and self.active_nnue_path and not force:
            return True
        if self._probe_task and not self._probe_task.done() and not force:
            await self._probe_task
            return self.compatibility_status == "matched"

        async def _run_probe() -> bool:
            self.compatibility_status = "probing"
            self.compatibility_report = []
            self.active_nnue_path = None
            self.last_startup_error = None

            if not os.path.exists(self.path):
                self.compatibility_status = "missing_engine"
                self.last_startup_error = f"Engine executable not found: {self.path}"
                self._publish_diagnostics(self.compatibility_status, self.last_startup_error)
                return False

            for candidate in self.configured_nnue_candidates:
                exists = os.path.exists(candidate)
                result: Dict[str, object] = {
                    "candidate": candidate,
                    "exists": exists,
                    "status": "missing" if not exists else "pending",
                }

                if not exists:
                    self.compatibility_report.append(result)
                    continue

                resolved_candidate = self._resolve_nnue_path(candidate)
                ok, error = await self._probe_single_candidate(resolved_candidate)
                if self._shutdown_requested:
                    self.compatibility_status = "shutdown"
                    return False
                result["resolved_candidate"] = resolved_candidate
                result["status"] = "matched" if ok else "rejected"
                result["error"] = error
                self.compatibility_report.append(result)

                if ok:
                    self.active_nnue_path = resolved_candidate
                    self.compatibility_status = "matched"
                    self.last_startup_error = None
                    self._publish_diagnostics("READY", None)
                    return True

            self.compatibility_status = "incompatible"
            self.last_startup_error = "No compatible engine/NNUE pair found."
            self._publish_diagnostics("INCOMPATIBLE", self.last_startup_error)
            return False

        self._probe_task = asyncio.create_task(_run_probe())
        await self._probe_task
        return self.compatibility_status == "matched"

    async def _probe_single_candidate(self, nnue_path: str) -> tuple[bool, Optional[str]]:
        try:
            self._probing_candidate = True
            await self._open_engine(nnue_path=nnue_path, perform_warmup=True)
            return True, None
        except Exception as exc:
            return False, str(exc)
        finally:
            self._probing_candidate = False
            await self.close()

    async def _open_engine(self, nnue_path: Optional[str], perform_warmup: bool) -> None:
        if self._shutdown_requested:
            raise RuntimeError("Engine service is shutting down.")
        self.last_internal_error = None
        self.last_startup_error = None

        logger.info(f"[EngineService] Initializing engine: {self.path}")
        self.process = await asyncio.create_subprocess_exec(
            self.path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.path.dirname(self.path),
        )
        self.running = True
        self.output_queue = queue.Queue(maxsize=max(1, int(config.ENGINE_OUTPUT_QUEUE_SIZE)))
        self.reader_task = asyncio.create_task(self._reader())

        await self.send("uci")
        await asyncio.wait_for(self._wait_for_line("uciok"), timeout=5.0)

        engine_opts = config._cfg.get("engine", {}).get("options", {
            "Skill Level": 15,
            "Hash": 128,
            "Threads": 2,
        })
        for name, value in engine_opts.items():
            await self.send(f"setoption name {name} value {value}")

        if nnue_path and os.path.exists(nnue_path):
            normalized_nnue_path = nnue_path.replace("\\", "/")
            await self.send(f"setoption name EvalFile value {normalized_nnue_path}")

        await self.send("isready")
        await asyncio.wait_for(self._wait_for_line("readyok"), timeout=5.0)

        if perform_warmup:
            self._drain_output_queue()
            await self.send("position startpos")
            await self.send("go depth 1")
            warmup_line = await asyncio.wait_for(self._wait_for_line("bestmove"), timeout=3.0)
            if "bestmove" not in warmup_line or "bestmove none" in warmup_line:
                raise RuntimeError(self.last_internal_error or f"Engine warmup failed: {warmup_line}")

        logger.info("[EngineService] engine pair validated successfully.")

    def _drain_output_queue(self) -> None:
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

    async def _get_output_line(self, timeout: float = 1.0) -> str:
        deadline = asyncio.get_running_loop().time() + max(0.0, float(timeout))
        while True:
            try:
                return self.output_queue.get_nowait()
            except queue.Empty:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise
                await asyncio.sleep(min(0.05, remaining))

    def _publish_diagnostics(self, status: str, error: Optional[str]) -> None:
        payload = {
            "engine": {
                "status": status,
                "error": error,
                "active_nnue_path": self.active_nnue_path,
                "compatibility_status": self.compatibility_status,
            }
        }
        try:
            bus.publish(BaseEvent.create(
                event_type=EventType.DIAGNOSTICS_UPDATED,
                source="engine_service",
                payload=payload,
            ))
        except Exception:
            logger.debug("[EngineService] failed to publish diagnostics", exc_info=True)

    async def start(self):
        """
        Start the engine with the already-probed compatible pair.
        """
        if self._shutdown_requested or self._closing:
            logger.warning("[EngineService] start skipped while engine service is shutting down.")
            return
        process = self.process
        if process and process.returncode is None:
            return

        ok = await self.probe_compatible_pair()
        if self._shutdown_requested or self._closing:
            logger.warning("[EngineService] start aborted because shutdown began during probe.")
            return
        if not ok or not self.active_nnue_path:
            self.last_startup_error = self.last_startup_error or "No compatible engine/NNUE pair found."
            logger.error(f"[EngineService] start aborted: {self.last_startup_error}")
            return

        try:
            await self._open_engine(nnue_path=self.active_nnue_path, perform_warmup=True)
        except (asyncio.TimeoutError, Exception) as exc:
            self.last_startup_error = str(exc)
            logger.error(f"[EngineService] startup failure: {exc}")
            await self.close()

    async def _reader(self):
        while self.running and self.process and self.process.stdout:
            try:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                self._enqueue_output_line(line)

                if line.startswith("info"):
                    event = EngineParser.parse_info_line(line)
                    if event:
                        bus.publish(event)

                if "ERROR" in line:
                    self.last_internal_error = line
                    if self._probing_candidate:
                        logger.warning(f"[EngineService] probe rejected candidate: {line}")
                    else:
                        logger.error(f"Engine Internal Error: {line}")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Reader Error: {exc}")
                break

    def _enqueue_output_line(self, line: str) -> None:
        try:
            self.output_queue.put_nowait(line)
            return
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self.output_queue.put_nowait(line)
        except queue.Full:
            logger.debug("[EngineService] output queue full; dropped latest engine line")

    async def _wait_for_line(self, target: str) -> str:
        while self.running:
            process = self.process
            if process is None:
                raise RuntimeError(f"Engine process closed before receiving: {target}")
            if process.returncode is not None:
                raise RuntimeError(f"Engine process died with code {process.returncode}")

            try:
                line = await self._get_output_line(timeout=1.0)
                if target in line:
                    return line
            except queue.Empty:
                continue

        raise RuntimeError(f"Engine stopped before receiving: {target}")

    async def send(self, cmd: str):
        process = self.process
        if process and process.stdin and not process.stdin.is_closing():
            try:
                process.stdin.write((cmd + "\n").encode("utf-8"))
                await process.stdin.drain()
            except Exception as exc:
                logger.debug(f"Send failed: {exc}")

    async def compute(self, fen: str, depth: int = 12, multipv: int = 1) -> Optional[dict]:
        async with self._get_compute_lock():
            return await self._compute_locked(fen, depth=depth, multipv=multipv)

    def _get_compute_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._compute_lock is None or self._compute_lock_loop is not loop:
            self._compute_lock = asyncio.Lock()
            self._compute_lock_loop = loop
        return self._compute_lock

    async def _compute_locked(self, fen: str, depth: int = 12, multipv: int = 1) -> Optional[dict]:
        process = self.process
        if self._shutdown_requested or self._closing:
            logger.warning("[EngineService] compute skipped while engine is closing.")
            return None

        if not process or process.returncode is not None:
            await self.start()
            process = self.process
            if not process or process.returncode is not None:
                return None

        if self.last_internal_error:
            logger.warning(f"Engine compute skipped due to startup error: {self.last_internal_error}")
            return None

        self._drain_output_queue()
        await self.send(f"setoption name MultiPV value {multipv}")
        await self.send("isready")

        try:
            await asyncio.wait_for(self._wait_for_line("readyok"), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            logger.debug("[EngineService] readyok wait timed out; continuing", exc_info=True)

        pos_cmd = "position startpos" if fen == "startpos" else f"position fen {fen}"
        await self.send(pos_cmd)
        await self.send(f"go depth {depth}")

        pv_lines = {}
        current_depth = 0
        final_best = "none"
        start_time = time.time()
        max_duration = 15.0

        try:
            while time.time() - start_time < max_duration:
                process = self.process
                if process is None:
                    logger.warning("[EngineService] compute interrupted because engine process was closed.")
                    break
                if process.returncode is not None:
                    break

                try:
                    line = await self._get_output_line(timeout=1.0)

                    if line.startswith("info"):
                        parts = line.split()
                        if "depth" in parts:
                            try:
                                d_val = int(parts[parts.index("depth") + 1])
                                if d_val > current_depth:
                                    current_depth = d_val
                            except Exception:
                                logger.debug("[EngineService] failed to parse depth", exc_info=True)

                        if "multipv" in parts and "score" in parts and "pv" in parts:
                            try:
                                rank = int(parts[parts.index("multipv") + 1])
                                score_idx = parts.index("score")
                                score_type = parts[score_idx + 1]
                                score_val = int(parts[score_idx + 2]) if score_type == "cp" else 9999
                                move = parts[parts.index("pv") + 1]
                                pv_lines[rank] = {"rank": rank, "move": move, "score_cp": score_val}
                            except Exception:
                                continue

                    if "bestmove" in line:
                        parts = line.split()
                        if len(parts) > 1:
                            final_best = parts[1]
                        break

                except queue.Empty:
                    if time.time() - start_time > 10.0:
                        await self.send("stop")

        except Exception as exc:
            logger.error(f"Computation error: {exc}")

        sorted_lines = sorted(pv_lines.values(), key=lambda item: item["rank"])
        return {
            "best_move": final_best,
            "score": pv_lines.get(1, {}).get("score_cp", 0),
            "depth": current_depth,
            "final": True,
            "is_thinking": False,
            "multi_pv": [
                {"move": line["move"], "score": line["score_cp"], "pv": [line["move"]]}
                for line in sorted_lines
            ],
        }

    async def is_healthy(self) -> bool:
        process = self.process
        if not process or process.returncode is not None:
            return False
        if self.last_internal_error:
            return False
        try:
            await self.send("isready")
            await asyncio.wait_for(self._wait_for_line("readyok"), timeout=1.0)
            return True
        except Exception:
            return False

    async def close(self):
        self._closing = True
        try:
            self.running = False
            process = self.process
            reader_task = self.reader_task
            if process:
                try:
                    if process.returncode is None:
                        await self.send("quit")
                        await asyncio.sleep(0.1)
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except Exception:
                    try:
                        process.kill()
                        await asyncio.wait_for(process.wait(), timeout=2.0)
                    except Exception:
                        logger.debug("[EngineService] failed to kill engine process", exc_info=True)

                if reader_task:
                    reader_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await reader_task
                if self.process is process:
                    self.process = None
                if self.reader_task is reader_task:
                    self.reader_task = None
                self.last_internal_error = None
                logger.info("Engine resources cleaned up.")
        finally:
            self._closing = False

    async def shutdown(self):
        """Cancel startup probes and close any active engine subprocess."""
        self._shutdown_requested = True
        current_task = asyncio.current_task()
        if self._probe_task and not self._probe_task.done() and self._probe_task is not current_task:
            self._probe_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._probe_task
        await self.close()
