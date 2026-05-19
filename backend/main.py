import os
from flask import Flask, render_template
from flask_socketio import SocketIO
from flask_cors import CORS

# System bootstrap (single authoritative wiring)
from backend.application.bootstrap import bootstrap_system
from backend.application.container import container
from backend.utils.logger import logger
from backend.utils import config
from backend.utils.error_response import build_error

def create_app():
    """
    [Interface Layer] Flask Application Factory.
    Initializes the Web UI and API Gateways.
    """
    app = Flask(
        __name__,
        template_folder="../frontend",
        static_folder="../frontend/static",
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = getattr(config, "SECRET_KEY", os.getenv("CHESS_SECRET_KEY", "industrial-secret"))
    app.config["MAX_CONTENT_LENGTH"] = int(getattr(config, "MAX_REQUEST_BYTES", 1_048_576))
    if getattr(config, "CORS_ALLOW_ALL", False):
        CORS(app, origins="*")
    elif getattr(config, "CORS_ALLOWED_ORIGINS", None):
        CORS(app, origins=getattr(config, "CORS_ALLOWED_ORIGINS"))

    # 1. System Bootstrap (The Core)
    bootstrap_system()

    # 2. Register Blueprints (Interfaces)
    from backend.interfaces.api.api_routes import api_bp
    from backend.interfaces.dashboard import dashboard_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(dashboard_bp)

    @app.errorhandler(413)
    def payload_too_large(_error):
        return build_error(
            "payload_too_large",
            "Request payload exceeds the configured size limit.",
            recoverable=False,
            details={"max_bytes": app.config["MAX_CONTENT_LENGTH"]},
        ), 413

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        return response

    @app.route("/")
    def serve_index():
        return render_template("index.html")

    # 3. Initialize WebSocket Gateway
    # NOTE: We intentionally keep `async_mode="threading"` to avoid implicit eventlet/gevent dependency.
    # Heavy background work is handled by our dedicated asyncio runtime thread.
    socketio_kwargs = {"async_mode": "threading"}
    if getattr(config, "CORS_ALLOW_ALL", False):
        socketio_kwargs["cors_allowed_origins"] = "*"
    elif getattr(config, "CORS_ALLOWED_ORIGINS", None):
        socketio_kwargs["cors_allowed_origins"] = getattr(config, "CORS_ALLOWED_ORIGINS")

    socketio = SocketIO(app, **socketio_kwargs)

    from backend.interfaces.websocket.socket_handler import register_socketio
    register_socketio(socketio)

    return app, socketio

if __name__ == "__main__":
    app, socketio = create_app()
    logger.info("S.M.A.R.T Chess Server Running on http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
