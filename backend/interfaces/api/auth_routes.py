from __future__ import annotations

from flask import current_app, jsonify

from backend.interfaces.api.shared import (
    api_bp,
    client_ip,
    config,
    error_response,
    json_object_payload,
    publish_security_event,
)


@api_bp.route("/login", methods=["POST"])
def login():
    """Local admin login used by the browser console gate."""
    try:
        payload = json_object_payload()
    except ValueError as exc:
        return error_response("validation_failed", str(exc), 400)
    password = str(payload.get("password", ""))
    if password != str(getattr(config, "ADMIN_PASSWORD", "")):
        publish_security_event("SECURITY.LOGIN_FAILED", {
            "username": str(payload.get("username", "admin"))[:64],
            "client": client_ip(),
            "reason": "invalid_credentials",
        })
        return error_response("invalid_credentials", "Invalid admin credentials.", 401, recoverable=True)

    try:
        from backend.utils.auth import create_jwt, decode_jwt_token, read_bearer_token, revoke_jwt_claims
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
    max_age = int(getattr(config, "JWT_TTL_MINUTES", 120)) * 60
    response = jsonify({
        "ok": True,
        "token": token,
        "role": "admin",
        "auth_mode": "cookie",
        "token_storage": "cookie",
        "expires_at": claims.get("exp"),
        "expires_in": max_age,
    })
    response.set_cookie(
        "token",
        token,
        max_age=max_age,
        httponly=True,
        secure=bool(getattr(config, "IS_PRODUCTION", False)),
        samesite="Strict",
    )
    return response


@api_bp.route("/logout", methods=["POST"])
def logout():
    try:
        from backend.utils.auth import read_bearer_token, decode_jwt_token, revoke_jwt_claims

        token = read_bearer_token()
        claims = decode_jwt_token(token, verify_revocation=False) if token else None
        revoked = revoke_jwt_claims(claims)
        if claims:
            publish_security_event("SECURITY.LOGOUT", {
                "client": client_ip(),
                "jti": claims.get("jti"),
                "sub": claims.get("sub"),
                "revoked": revoked,
            })
    except Exception:
        current_app.logger.debug("Failed to revoke JWT during logout", exc_info=True)
    response = jsonify({"ok": True})
    response.delete_cookie("token", samesite="Strict")
    return response
