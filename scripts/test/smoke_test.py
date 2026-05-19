import os
import sys
import requests


sys.path.append(os.getcwd())
try:
    from backend.utils import config
except Exception:
    config = None

BASE_URL = os.environ.get("SMART_CHESS_BASE_URL", "http://127.0.0.1:5000")
ADMIN_PASSWORD = (
    os.environ.get("SMART_CHESS_ADMIN_PASSWORD")
    or os.environ.get("ADMIN_PASSWORD")
    or getattr(config, "ADMIN_PASSWORD", "888888")
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

    print("Smoke test completed successfully.")


if __name__ == "__main__":
    run_smoke_test()
