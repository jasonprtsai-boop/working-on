from flask import Blueprint, jsonify, send_from_directory
import os

from backend.utils.auth import verify_request_token
from backend.utils.error_response import build_error


dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/dashboard/static',
)

ROLE_LEVELS = {"viewer": 1, "operator": 2, "admin": 3}


def _require_dashboard_access():
    claims = verify_request_token()
    if not claims:
        return jsonify(build_error("unauthorized", "Valid bearer token required.")), 401
    if ROLE_LEVELS.get(str(claims.get("role", "")).lower(), 0) < ROLE_LEVELS["operator"]:
        return jsonify(build_error("forbidden", "Operator role required.")), 403
    return None

@dashboard_bp.route('/dashboard')
def index():
    denied = _require_dashboard_access()
    if denied:
        return denied
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), 'index.html')
