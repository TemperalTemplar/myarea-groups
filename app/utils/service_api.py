import hmac
import logging
from functools import wraps
from flask import request, jsonify, current_app

log = logging.getLogger(__name__)


def _get_key():
    key = current_app.config.get("SERVICE_API_KEY", "")
    if not key:
        raise RuntimeError("SERVICE_API_KEY not set")
    return key


def _make_auth_header():
    return {"X-Service-Key": _get_key(), "X-Service-Name": "groups", "Content-Type": "application/json"}


def require_service_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        incoming = request.headers.get("X-Service-Key", "")
        try:
            expected = _get_key()
        except RuntimeError:
            return jsonify({"error": "Service key not configured"}), 500
        if not incoming or not hmac.compare_digest(incoming.encode(), expected.encode()):
            log.warning("Service key mismatch from %s", request.remote_addr)
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper
