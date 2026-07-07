from __future__ import annotations

import os
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify
from backend.utils.logger import logger
from backend.utils import config

SECRET_KEY = getattr(config, "SECRET_KEY", None) or os.getenv("CHESS_SECRET_KEY", "industrial-secret")
_revoked_jtis: dict[str, float] = {}


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _purge_expired_revocations(now_ts: float | None = None) -> None:
    now = _now_ts() if now_ts is None else float(now_ts)
    expired = [jti for jti, exp_ts in _revoked_jtis.items() if exp_ts <= now]
    for jti in expired:
        _revoked_jtis.pop(jti, None)


def create_jwt(role, *, subject="admin", ttl_minutes: int | None = None):
    now = datetime.now(timezone.utc)
    ttl = int(ttl_minutes or getattr(config, "JWT_TTL_MINUTES", 120))
    payload = {
        'role': role,
        'sub': str(subject or role or "user"),
        'iat': now,
        'jti': str(uuid.uuid4()),
        'exp': now + timedelta(minutes=ttl)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')


def is_token_revoked(claims: dict | None) -> bool:
    if not claims:
        return True
    _purge_expired_revocations()
    jti = claims.get("jti")
    return bool(jti and _revoked_jtis.get(str(jti), 0) > _now_ts())


def revoke_jwt_claims(claims: dict | None) -> bool:
    if not claims or not claims.get("jti"):
        return False
    try:
        exp_ts = float(claims.get("exp") or _now_ts())
    except Exception:
        exp_ts = _now_ts()
    _revoked_jtis[str(claims["jti"])] = max(exp_ts, _now_ts())
    _purge_expired_revocations()
    return True


def revoke_jwt_token(token: str | None) -> bool:
    claims = decode_jwt_token(token, verify_revocation=False)
    return revoke_jwt_claims(claims)


def decode_jwt_token(token, *, verify_revocation: bool = True):
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        if verify_revocation and is_token_revoked(claims):
            return None
        return claims
    except Exception:
        return None


def normalize_bearer_token(value):
    if not value:
        return None
    token = str(value).strip()
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()
    return token or None


def read_bearer_token():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return normalize_bearer_token(auth_header)
    return request.cookies.get('token')


def verify_request_token():
    token = read_bearer_token()
    if not token:
        return None
    return decode_jwt_token(token)


def verify_socket_token(auth=None):
    token = None
    if isinstance(auth, dict):
        token = (
            auth.get("token")
            or auth.get("access_token")
            or auth.get("Authorization")
            or auth.get("authorization")
        )

    token = normalize_bearer_token(token)
    if not token:
        try:
            token = read_bearer_token()
        except RuntimeError:
            token = None
    if not token:
        return None
    return decode_jwt_token(token)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = read_bearer_token()
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            data = decode_jwt_token(token)
            if not data:
                return jsonify({'message': 'Token is invalid!'}), 401
            # You can add role check here if needed
            request.user_role = data.get('role')
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!'}), 401

        return f(*args, **kwargs)
    return decorated
