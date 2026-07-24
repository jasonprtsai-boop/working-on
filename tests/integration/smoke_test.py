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


def run_smoke_test():
    print("Running manual integration smoke test ...")
    auth_headers = get_auth_headers()
    protected = {"/api/health", "/api/state", "/api/vision/status", "/api/engine/status"}
    for path in ("/api/ready", "/api/health", "/api/state", "/api/vision/status", "/api/engine/status"):
        response = requests.get(
            f"{BASE_URL}{path}",
            headers=auth_headers if path in protected else None,
            timeout=10,
        )
        print(f"GET {path}: {response.status_code}")
        response.raise_for_status()

    response = requests.post(
        f"{BASE_URL}/api/control",
        json={"action": "start_engine", "payload": {"source": "integration-smoke"}},
        headers=auth_headers,
        timeout=10,
    )
    print(f"POST /api/control: {response.status_code}")
    response.raise_for_status()
    return True


if __name__ == "__main__":
    print(f"Make sure the server is running on {BASE_URL}")
    run_smoke_test()
