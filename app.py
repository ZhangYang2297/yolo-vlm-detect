import sys
import atexit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, Response, stream_with_context, request
from flask_cors import CORS
from prometheus_flask_exporter import PrometheusMetrics
from config.settings import get_settings
from core.logger import setup_logging, get_logger
from core.db import init_db
from core.redis_client import subscribe
from web.routes.views import views_bp
from web.routes.api import api_bp
import json
import time

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


def create_app():
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["SECRET_KEY"] = settings.flask.secret_key
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB上传

    CORS(app)

    init_db(app)

    metrics = PrometheusMetrics(app)
    metrics.info("app_info", "AI视频智能分析系统", version="1.0.0")

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    Path(settings.chroma.persist_path).mkdir(parents=True, exist_ok=True)

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
