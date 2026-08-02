from pathlib import Path
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase
from config.settings import get_settings
from core.logger import get_logger

logger = get_logger(__name__)

db = SQLAlchemy()
migrate = Migrate()


class Base(DeclarativeBase):
    pass


def _get_db_uri() -> str:
    settings = get_settings()
    return (
        f"mysql+pymysql://{settings.mysql.user}:{settings.mysql.password}"
        f"@{settings.mysql.host}:{settings.mysql.port}/{settings.mysql.database}"
        f"?charset=utf8mb4"
    )


def init_db(app=None, create_tables: bool = False):
    settings = get_settings()
    db_uri = _get_db_uri()

    if app:
        app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_size": 10,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
        }
        db.init_app(app)
        if create_tables:
            with app.app_context():
                db.create_all()
                logger.info("mysql_tables_created", host=settings.mysql.host, port=settings.mysql.port)
        logger.info("mysql_initialized", host=settings.mysql.host, port=settings.mysql.port)
    else:
        engine = create_engine(db_uri, pool_pre_ping=True)
        if create_tables:
            Base.metadata.create_all(engine)
            logger.info("mysql_tables_created_standalone", host=settings.mysql.host, port=settings.mysql.port)
        logger.info("mysql_initialized_standalone", host=settings.mysql.host, port=settings.mysql.port)

    return db


def init_migrate(app):
    """Registers Flask-Migrate with the app (call after init_db)."""
    from flask_migrate import Migrate as _Migrate
    return _Migrate(app, db)
