import sys
import os
from typing import Optional

# Redirect to the modular application entry point
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

if __name__ == "__main__":
    from backend.main import create_app
    from backend.utils import config
    app, socketio = create_app()

    def _truthy(v: Optional[str]) -> bool:
        return str(v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    debug = _truthy(os.getenv("FLASK_DEBUG")) or _truthy(os.getenv("DEBUG"))
    host = getattr(config, "BIND_HOST", os.getenv("HOST", "127.0.0.1"))
    port = int(getattr(config, "PORT", os.getenv("PORT", "5000")))
    print(f"\nS.M.A.R.T. Chess Robot is running: http://{host}:{port}/\n", flush=True)
    # This project is served locally through Flask-SocketIO's threading mode.
    # Flask-SocketIO requires this flag when using Werkzeug outside debug mode.
    socketio.run(
        app,
        host=host,
        debug=debug,
        use_reloader=False,
        port=port,
        allow_unsafe_werkzeug=not getattr(config, "IS_PRODUCTION", False),
    )
