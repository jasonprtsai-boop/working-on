from __future__ import annotations

import hmac
import ipaddress

from flask import request

from backend.interfaces.api.shared import config


def vision_source_diagnostics(camera: dict, source: str) -> dict:
    robot_status = robot_control_status()
    control_connected = bool(robot_status.get("connected") or robot_status.get("is_connected"))
    fake_robot = bool(getattr(config, "FAKE_ROBOT", True))
    control_status = "simulation" if fake_robot else ("connected" if control_connected else "offline")
    vision_connected = bool(camera.get("connected") or camera.get("opened"))
    vision_running = bool(camera.get("running"))
    key_configured = bool(str(getattr(config, "VISION_TMFLOW_INGEST_KEY", "") or "").strip())
    key_status = tmflow_vision_ingest_key_status(source=source, key_configured=key_configured)
    tmvision_http = str(source or "").strip().lower() == "tmvision_http"

    return {
        "control_channel": {
            "label": "5890 control",
            "adapter": str(getattr(config, "ROBOT_ADAPTER", "tmflow_json")),
            "host": str(getattr(config, "ROBOT_IP", "")),
            "port": int(getattr(config, "ROBOT_PORT", 5890)),
            "endpoint": f"{getattr(config, 'ROBOT_IP', '')}:{getattr(config, 'ROBOT_PORT', 5890)}",
            "connected": control_connected,
            "status": control_status,
            "fake_robot": fake_robot,
            "last_error": robot_status.get("last_error") or robot_status.get("error"),
        },
        "vision_channel": {
            "label": "TMvision HTTP" if tmvision_http else "5891 vision",
            "source": source,
            "host": str(getattr(config, "BIND_HOST", "")) if tmvision_http else str(getattr(config, "VISION_TMFLOW_IMAGE_HOST", "")),
            "port": int(getattr(config, "PORT", 5000)) if tmvision_http else int(getattr(config, "VISION_TMFLOW_IMAGE_PORT", 5891)),
            "endpoint": camera.get("endpoint")
            or (
                "/api/vision/tmvision/detect"
                if tmvision_http
                else f"{getattr(config, 'VISION_TMFLOW_IMAGE_HOST', '')}:{getattr(config, 'VISION_TMFLOW_IMAGE_PORT', 5891)}"
            ),
            "connected": vision_connected,
            "running": vision_running,
            "status": "ready" if tmvision_http and vision_running else ("connected" if vision_connected else ("starting" if vision_running else "offline")),
            "frames_received": int(camera.get("frames_received") or 0),
            "last_frame_age_sec": camera.get("last_frame_age_sec"),
            "last_frame_at": camera.get("last_frame_at"),
            "reconnects": int(camera.get("reconnects") or 0),
            "decode_failures": int(camera.get("decode_failures") or 0),
            "dropped_frames": int(camera.get("dropped_frames") or 0),
            "fps_limit": float(camera.get("fps_limit") or getattr(config, "VISION_TMFLOW_IMAGE_FPS_LIMIT", 2.0)),
            "last_error": camera.get("last_error"),
        },
        "socket_ingest_channel": tmflow_socket_ingest_status(),
        "ingest_key": key_status,
    }


def tmflow_socket_ingest_status() -> dict:
    max_age = float(getattr(config, "TMFLOW_INGEST_TELEMETRY_MAX_AGE_SEC", 3.0))
    status = {
        "label": "5892 TMflow push",
        "enabled": bool(getattr(config, "TMFLOW_INGEST_SERVER_ENABLED", False)),
        "host": str(getattr(config, "TMFLOW_INGEST_SERVER_HOST", "")),
        "port": int(getattr(config, "TMFLOW_INGEST_SERVER_PORT", 5892)),
        "endpoint": f"{getattr(config, 'TMFLOW_INGEST_SERVER_HOST', '')}:{getattr(config, 'TMFLOW_INGEST_SERVER_PORT', 5892)}",
        "key_configured": bool(str(getattr(config, "TMFLOW_INGEST_KEY", "") or "").strip()),
    }
    if not status["enabled"]:
        try:
            from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state

            status["running"] = False
            status["telemetry"] = tmflow_ingest_state.status(max_age_sec=max_age)
        except Exception:
            status["running"] = False
        status["status"] = "disabled"
        return status
    try:
        from backend.application.container import container
        from backend.infrastructure.robot.tmflow_ingest_state import tmflow_ingest_state

        server = container.get("tmflow_ingest_server")
        if server and hasattr(server, "get_status"):
            status.update(dict(server.get_status()))
        else:
            status["running"] = False
            status["telemetry"] = tmflow_ingest_state.status(max_age_sec=max_age)
    except Exception as exc:
        status.update({"running": False, "last_error": str(exc)})
    status["status"] = (
        "connected"
        if (status.get("running") and (status.get("telemetry") or {}).get("connected"))
        else ("listening" if status.get("running") else ("disabled" if not status.get("enabled") else "offline"))
    )
    return status


def robot_control_status() -> dict:
    try:
        from backend.application.container import container

        robot = container.get("robot")
        if robot and hasattr(robot, "get_status"):
            status = robot.get_status() or {}
            if isinstance(status, dict):
                return dict(status)
    except Exception as exc:
        return {"connected": False, "error": str(exc)}
    return {"connected": False}


def tmflow_vision_ingest_key_status(*, source: str, key_configured: bool) -> dict:
    source = str(source or "").strip().lower()
    bind_host = str(getattr(config, "BIND_HOST", "127.0.0.1") or "").strip()
    fake_robot = bool(getattr(config, "FAKE_ROBOT", True))
    exposed_network = bind_host in {"0.0.0.0", "::"}
    required = source in {"tmvision_http", "tmflow_json"} and (
        bool(getattr(config, "IS_PRODUCTION", False)) or exposed_network or not fake_robot
    )
    return {
        "configured": bool(key_configured),
        "required": bool(required),
        "ok": bool((not required) or key_configured),
        "exposed_network": bool(exposed_network),
        "fake_robot": fake_robot,
    }


def tmflow_frame_ingest_authorized() -> bool:
    try:
        from backend.utils.auth import verify_request_token

        claims = verify_request_token()
        if str((claims or {}).get("role") or "").lower() in {"operator", "setup", "admin"}:
            return True
    except Exception:
        pass

    expected_key = str(getattr(config, "VISION_TMFLOW_INGEST_KEY", "") or "").strip()
    provided_key = str(
        request.headers.get("X-TMflow-Key")
        or request.headers.get("X-TMflow-Vision-Key")
        or request.args.get("key")
        or request.args.get("stream_key")
        or request.form.get("key")
        or request.form.get("stream_key")
        or request.form.get("tmflow_key")
        or request.form.get("tmflow_vision_key")
        or ""
    ).strip()
    if expected_key:
        return hmac.compare_digest(provided_key, expected_key)

    if getattr(config, "IS_PRODUCTION", False):
        return False

    remote = str(request.remote_addr or "").strip()
    trusted_hosts = {
        "127.0.0.1",
        "::1",
        str(getattr(config, "ROBOT_IP", "") or "").strip(),
        str(getattr(config, "ROBOT_PC_IP", "") or "").strip(),
    }
    if remote in trusted_hosts:
        return True
    try:
        remote_ip = ipaddress.ip_address(remote)
        return bool(remote_ip.is_loopback or remote_ip.is_link_local)
    except ValueError:
        return False
