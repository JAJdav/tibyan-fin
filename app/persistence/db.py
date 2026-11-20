from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.mysql_url, pool_size=settings.mysql_pool_size,
                                max_overflow=settings.mysql_max_overflow,
                                pool_recycle=settings.mysql_pool_recycle_s,
                                pool_pre_ping=True, future=True)
    return _engine


def db_ok() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
