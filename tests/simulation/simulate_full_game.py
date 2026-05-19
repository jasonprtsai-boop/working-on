import os


os.environ.setdefault("FAKE_VISION", "1")

from backend.main import create_app
from backend.utils import config


def simulate_full_game(rounds: int = 10):
    app, _socketio = create_app()
    client = app.test_client()
    login = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
    token = (login.get_json() or {}).get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    print(f"Simulating {rounds} backend control cycles ...")
    for index in range(rounds):
        response = client.post(
            "/api/control",
            json={"action": "start_engine", "payload": {"turn": index + 1}},
            headers=headers,
        )
        print(f"Round {index + 1}: /api/control -> {response.status_code}")
        state = client.get("/api/state", headers=headers).get_json() or {}
        print(f"State alias: {state.get('state')} | FEN: {state.get('fen', '')[:24]}...")


if __name__ == "__main__":
    simulate_full_game()
