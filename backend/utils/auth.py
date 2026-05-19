import os
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify
from backend.utils.logger import logger
from backend.utils import config

SECRET_KEY = getattr(config, "SECRET_KEY", None) or os.getenv("CHESS_SECRET_KEY", "industrial-secret")

def create_jwt(role, *, subject="admin"):
    now = datetime.now(timezone.utc)
    payload = {
        'role': role,
        'sub': str(subject or role or "user"),
        'iat': now,
        'jti': str(uuid.uuid4()),
        'exp': now + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')


def decode_jwt_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
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
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            # You can add role check here if needed
            request.user_role = data.get('role')
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!'}), 401

        return f(*args, **kwargs)
    return decorated
