import os
import sys
import time


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("FAKE_VISION", "1")

from backend.main import create_app
from backend.utils import config


class BackendSimulationDriver:
    def __init__(self):
        self.app, _socketio = create_app()
        self.client = self.app.test_client()
        login = self.client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
        token = (login.get_json() or {}).get("token")
        self.auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    def run_cycle(self, rounds: int = 5):
        print(f"Running backend simulation cycle for {rounds} rounds ...")
        for index in range(rounds):
            print(f"\n--- Round {index + 1}/{rounds} ---")
            for path in ("/api/ready", "/api/health", "/api/state", "/api/vision/status", "/api/engine/status"):
                headers = None if path == "/api/ready" else self.auth_headers
                response = self.client.get(path, headers=headers)
                print(f"{path}: {response.status_code}")
            control = self.client.post(
                "/api/control",
                json={"action": "START", "payload": {"round": index + 1}},
                headers=self.auth_headers,
            )
            print(f"/api/control: {control.status_code}")
            time.sleep(0.1)


if __name__ == "__main__":
    BackendSimulationDriver().run_cycle()
