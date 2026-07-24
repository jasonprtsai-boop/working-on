import os
import time
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


def stress_test(rounds=20):
    print(f"Starting backend endpoint stress test: {rounds} rounds")
    success_count = 0
    endpoints = ["/api/health", "/api/state", "/api/engine/status"]
    auth_headers = get_auth_headers()
    protected = {"/api/health", "/api/state", "/api/engine/status"}

    for round_index in range(rounds):
        round_ok = True
        for path in endpoints:
            response = requests.get(
                f"{BASE_URL}{path}",
                headers=auth_headers if path in protected else None,
                timeout=10,
            )
            if response.status_code != 200:
                round_ok = False
                print(f"Round {round_index + 1}: {path} failed with {response.status_code}")
                break
        if round_ok:
            success_count += 1
        time.sleep(0.05)

    print(f"Completed {success_count}/{rounds} successful rounds")


if __name__ == "__main__":
    stress_test()
