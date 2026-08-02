import uuid
from flask import jsonify


def success_response(data, status_code: int = 200):
    """Return a unified success response."""
    return jsonify({
        "success": True,
        "data": data,
        "request_id": str(uuid.uuid4()),
    }), status_code


def error_response(code: str, message: str, status_code: int = 400):
    """Return a unified error response."""
    return jsonify({
        "success": False,
        "error": {"code": code, "message": message},
        "request_id": str(uuid.uuid4()),
    }), status_code
