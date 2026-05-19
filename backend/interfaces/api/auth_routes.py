from __future__ import annotations

from flask import current_app, jsonify, request

from backend.interfaces.api.shared import (
    api_bp,
    client_ip,
    config,
    error_response,
    publish_security_event,
)


@api_bp.route("/login", methods=["POST"])
def login():
    """Local admin login used by the browser console gate."""
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password", ""))
    if password != str(getattr(config, "ADMIN_PASSWORD", "")):
        publish_security_event("SECURITY.LOGIN_FAILED", {
            "username": str(payload.get("username", "admin"))[:64],
            "client": client_ip(),
            "reason": "invalid_credentials",
        })
        return error_response("invalid_credentials", "Invalid admin credentials.", 401, recoverable=True)

    try:
        from backend.utils.auth import create_jwt, decode_jwt_token
    except ModuleNotFoundError:
        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        token = serializer.dumps({"role": "admin"}, salt="admin-login")
        return jsonify({"ok": True, "token": token, "role": "admin"})

    token = create_jwt("admin", subject=str(payload.get("username") or "admin"))
    claims = decode_jwt_token(token) or {}
    publish_security_event("SECURITY.LOGIN_SUCCEEDED", {
        "username": str(payload.get("username", "admin"))[:64],
        "client": client_ip(),
        "jti": claims.get("jti"),
        "sub": claims.get("sub"),
    })
    response = jsonify({"ok": True, "token": token, "role": "admin"})
    response.set_cookie(
        "token",
        token,
        max_age=24 * 60 * 60,
        httponly=True,
        secure=bool(getattr(config, "IS_PRODUCTION", False)),
        samesite="Strict",
    )
    return response


@api_bp.route("/logout", methods=["POST"])
def logout():
    response = jsonify({"ok": True})
    response.delete_cookie("token", samesite="Strict")
    return response
