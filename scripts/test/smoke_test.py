import os
import sys
import requests


sys.path.append(os.getcwd())
try:
    from backend.utils import config
except Exception:
    config = None

BASE_URL = os.environ.get("SMART_CHESS_BASE_URL", "http://127.0.0.1:5000")
REQUIRE_HARDWARE_READY = str(os.environ.get("SMART_CHESS_REQUIRE_HARDWARE_READY", "")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ADMIN_PASSWORD = (
    os.environ.get("SMART_CHESS_ADMIN_PASSWORD")
    or os.environ.get("ADMIN_PASSWORD")
    or getattr(config, "ADMIN_PASSWORD", "login")
)


def get_auth_headers():
    response = requests.post(
        f"{BASE_URL}/api/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    token = response.json().get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def report_readiness(payload, *, require_hardware_ready=REQUIRE_HARDWARE_READY):
    if not isinstance(payload, dict):
        print("Hardware readiness: UNKNOWN (ready response was not JSON)")
        if require_hardware_ready:
            raise RuntimeError("Hardware readiness is required but could not be read.")
        return

    ready = bool(payload.get("ready"))
    bootstrap = payload.get("bootstrap", {}) if isinstance(payload.get("bootstrap"), dict) else {}
    robot_connected = bool(payload.get("robot_connected"))
    bootstrap_ready = bool(bootstrap.get("ready"))
    if ready:
        print("Hardware readiness: READY")
        return

    print(
        "Hardware readiness: NOT READY "
        f"(ready={ready}, bootstrap={bootstrap_ready}, robot_connected={robot_connected})"
    )
    for item in bootstrap.get("errors", []) or []:
        if not isinstance(item, dict):
            continue
        print(f"  - {item.get('component')}: {item.get('error')}")

    if require_hardware_ready:
        raise RuntimeError("Hardware readiness is required but /api/ready reports not ready.")


def report_health(payload, *, require_hardware_ready=REQUIRE_HARDWARE_READY):
    if isinstance(payload, dict) and payload.get("ok") is False:
        print("Health payload reports ok=false; software endpoints are reachable but readiness is degraded.")
        if require_hardware_ready:
            raise RuntimeError("Hardware readiness is required but /api/health reports degraded.")


def response_payload(response):
    try:
        return response.json()
    except Exception:
        return None


def run_smoke_test():
    print("Starting HTTP smoke test ...")
    auth_headers = get_auth_headers()
    endpoints = [
        ("GET", "/api/ready", None),
        ("GET", "/api/health", None),
        ("GET", "/api/state", None),
        ("GET", "/api/vision/status", None),
        ("GET", "/api/engine/status", None),
        ("POST", "/api/control", {"action": "START", "payload": {"source": "smoke"}}),
    ]

    for method, path, payload in endpoints:
        url = f"{BASE_URL}{path}"
        headers = auth_headers if path != "/api/ready" else None
        response = requests.request(method, url, json=payload, headers=headers, timeout=10)
        print(f"{method} {path}: {response.status_code}")
        response.raise_for_status()
        body = response_payload(response)
        if path == "/api/ready":
            report_readiness(body)
        elif path == "/api/health":
            report_health(body)

    if REQUIRE_HARDWARE_READY:
        print("Smoke test completed successfully with hardware readiness.")
    else:
        print("Smoke test completed successfully for software endpoints. Hardware readiness is reported separately above.")


if __name__ == "__main__":
    run_smoke_test()
