from __future__ import annotations

import os
import jwt
import uuid
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify
from backend.utils.logger import logger
from backend.utils import config

SECRET_KEY = getattr(config, "SECRET_KEY", None) or os.getenv("CHESS_SECRET_KEY", "industrial-secret")
_revoked_jtis: dict[str, float] = {}
_REVOCATION_LOCK = threading.RLock()
_REVOCATION_SCHEMA_READY: set[str] = set()


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _purge_expired_revocations(now_ts: float | None = None) -> None:
    now = _now_ts() if now_ts is None else float(now_ts)
    with _REVOCATION_LOCK:
        expired = [jti for jti, exp_ts in _revoked_jtis.items() if exp_ts <= now]
        for jti in expired:
            _revoked_jtis.pop(jti, None)
        db_path = _revocation_db_path()
        if not _use_persistent_revocation_store(db_path):
            return
        try:
            with _revocation_connection(db_path) as conn:
                conn.execute("DELETE FROM jwt_revocations WHERE exp_ts <= ?", (now,))
        except Exception:
            logger.warning("[auth] failed to purge expired JWT revocations", exc_info=True)


def _revocation_db_path() -> str:
    return str(getattr(config, "JWT_REVOCATION_DB_PATH", getattr(config, "DB_PATH", ":memory:")) or ":memory:")


def _use_persistent_revocation_store(db_path: str | None = None) -> bool:
    path = str(db_path if db_path is not None else _revocation_db_path()).strip()
    return bool(path and path != ":memory:")


def _revocation_connection(db_path: str):
    path = os.path.abspath(db_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    if path not in _REVOCATION_SCHEMA_READY:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jwt_revocations (
                jti TEXT PRIMARY KEY,
                exp_ts REAL NOT NULL,
                revoked_at REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jwt_revocations_exp_ts ON jwt_revocations(exp_ts)")
        conn.commit()
        _REVOCATION_SCHEMA_READY.add(path)
    return conn


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


def create_scoped_jwt(scope: str, *, role: str = "operator", subject: str = "scoped", ttl_seconds: int = 300):
    now = datetime.now(timezone.utc)
    payload = {
        "role": str(role or "operator"),
        "sub": str(subject or scope or "scoped"),
        "scope": str(scope or ""),
        "iat": now,
        "jti": str(uuid.uuid4()),
        "exp": now + timedelta(seconds=max(1, int(ttl_seconds or 300))),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def is_token_revoked(claims: dict | None) -> bool:
    if not claims:
        return True
    _purge_expired_revocations()
    jti = claims.get("jti")
    if not jti:
        return False
    jti_text = str(jti)
    now = _now_ts()
    with _REVOCATION_LOCK:
        if _revoked_jtis.get(jti_text, 0) > now:
            return True
        db_path = _revocation_db_path()
        if not _use_persistent_revocation_store(db_path):
            return False
        try:
            with _revocation_connection(db_path) as conn:
                row = conn.execute(
                    "SELECT exp_ts FROM jwt_revocations WHERE jti = ?",
                    (jti_text,),
                ).fetchone()
            return bool(row and float(row[0]) > now)
        except Exception:
            logger.warning("[auth] failed to query JWT revocation store", exc_info=True)
            return False


def revoke_jwt_claims(claims: dict | None) -> bool:
    if not claims or not claims.get("jti"):
        return False
    try:
        exp_ts = float(claims.get("exp") or _now_ts())
    except Exception:
        exp_ts = _now_ts()
    jti = str(claims["jti"])
    now = _now_ts()
    expires_at = max(exp_ts, now)
    with _REVOCATION_LOCK:
        _revoked_jtis[jti] = expires_at
        db_path = _revocation_db_path()
        if _use_persistent_revocation_store(db_path):
            try:
                with _revocation_connection(db_path) as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO jwt_revocations (jti, exp_ts, revoked_at)
                        VALUES (?, ?, ?)
                        """,
                        (jti, expires_at, now),
                    )
            except Exception:
                logger.warning("[auth] failed to persist JWT revocation", exc_info=True)
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
