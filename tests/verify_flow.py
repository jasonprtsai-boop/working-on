import os
import requests


BASE_URL = os.environ.get("SMART_CHESS_BASE_URL", "http://127.0.0.1:5000")
ADMIN_PASSWORD = os.environ.get("SMART_CHESS_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "888888")


def get_auth_headers():
    response = requests.post(
        f"{BASE_URL}/api/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    token = response.json().get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def test_flow():
    print("Verifying current backend flow ...")
    auth_headers = get_auth_headers()
    protected_paths = {
        "/api/health",
        "/api/estop/status",
        "/api/control",
        "/api/estop/trigger",
        "/api/estop/reset",
    }
    steps = [
        ("GET", "/api/ready", None),
        ("GET", "/api/health", None),
        ("GET", "/api/state", None),
        ("GET", "/api/estop/status", None),
        ("POST", "/api/control", {"action": "start_engine", "payload": {"source": "verify_flow"}}),
        ("POST", "/api/estop/trigger", {"reason": "verify-flow"}),
        ("POST", "/api/estop/reset", None),
    ]

    for method, path, payload in steps:
        response = requests.request(
            method,
            f"{BASE_URL}{path}",
            json=payload,
            headers=auth_headers if path in protected_paths else None,
            timeout=10,
        )
        print(f"{method} {path}: {response.status_code}")
        response.raise_for_status()


if __name__ == "__main__":
    test_flow()
