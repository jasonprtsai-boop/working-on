import os
import sys


sys.path.append(os.getcwd())
os.environ.setdefault("FAKE_VISION", "1")

from backend.main import create_app
from backend.utils import config


def _auth_headers(client):
    response = client.post("/api/login", json={"username": "admin", "password": config.ADMIN_PASSWORD})
    token = (response.get_json() or {}).get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def test_export():
    print("Testing export endpoint ...")
    app, _socketio = create_app()
    client = app.test_client()

    response = client.get("/api/export/excel", headers=_auth_headers(client))
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    if response.status_code == 200:
        print(f"Bytes: {len(response.data)}")


if __name__ == "__main__":
    test_export()
