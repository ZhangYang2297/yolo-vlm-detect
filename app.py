import sys
import atexit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, Response, stream_with_context
from flask_cors import CORS
from prometheus_flask_exporter import PrometheusMetrics
from config.settings import get_settings
from core.logger import setup_logging, get_logger
from core.db import init_db, init_migrate
from core.redis_client import subscribe
from core.runtime_manager import RuntimeManager
from web.routes.views import views_bp
from web.routes.api import api_bp
from web.routes.video_sources import video_sources_bp
from web.routes.analysis_tasks import analysis_tasks_bp
from web.routes.runtime import runtime_bp
from web.routes.monitor import monitor_bp
from web.routes.monitor_views import monitor_views_bp
import json
import time

setup_logging()
logger = get_logger(__name__)
settings = get_settings()

_metrics = None


def create_app(register_metrics: bool = True):
    global _metrics
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["SECRET_KEY"] = settings.flask.secret_key
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

    CORS(app)
    init_db(app)
    init_migrate(app)
    app.extensions["runtime_manager"] = RuntimeManager()

    if register_metrics and _metrics is None:
        _metrics = PrometheusMetrics(app)
        _metrics.info("app_info", "AI\u89c6\u9891\u667a\u80fd\u5206\u6790\u7cfb\u7edf", version="1.0.0")

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(video_sources_bp)
    app.register_blueprint(analysis_tasks_bp)
    app.register_blueprint(runtime_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(monitor_views_bp)

    Path(settings.chroma.persist_path).mkdir(parents=True, exist_ok=True)

    # Global JSON error handler for /api/* so unexpected exceptions never
    # leak an HTML error page (which breaks front-end JSON.parse).
    from werkzeug.exceptions import HTTPException
    from flask import request as _req, jsonify as _jsonify

    @app.errorhandler(Exception)
    def _api_json_error(err):
        if not _req.path.startswith("/api/"):
            raise err  # let Flask handle non-API paths normally
        if isinstance(err, HTTPException):
            code = err.code or 500
            body = {"success": False, "error": {"code": err.name.upper().replace(" ", "_"),
                                                 "message": err.description}}
            return _jsonify(body), code
        logger.exception("api_unhandled_error", path=_req.path)
        return _jsonify({
            "success": False,
            "error": {"code": "INTERNAL_ERROR", "message": str(err) or "Internal Server Error"},
        }), 500

    @app.route("/favicon.ico")
    def _favicon():
        return ("", 204)

    @app.route("/events")
    def sse_events():
        def generate():
            pubsub = subscribe("alarm:new")
            for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @app.route("/health")
    def health():
        return {"status": "ok", "timestamp": time.time()}

    logger.info("app_started", port=settings.flask.port, env=settings.flask.env)
    return app


app = create_app()


if __name__ == "__main__":
    if settings.flask.env == "development":
        app.run(host="0.0.0.0", port=settings.flask.port, debug=True, use_reloader=False)
    else:
        from waitress import serve
        logger.info("starting_waitress_production_server")
        serve(app, host="0.0.0.0", port=settings.flask.port, threads=8)
