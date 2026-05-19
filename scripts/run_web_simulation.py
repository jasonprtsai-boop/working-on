import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("FAKE_VISION", "1")
os.environ.setdefault("FAKE_ROBOT", "1")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "1")

from backend.main import create_app


def main():
    app, socketio = create_app()
    host = "0.0.0.0"
    port = 5000
    print("Starting local web simulation server ...")
    print(f"Open http://127.0.0.1:{port}")
    socketio.run(app, host=host, port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
