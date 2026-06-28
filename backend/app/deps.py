from app.config import load_config
from app.db import make_engine, make_session_factory

_config = None
_engine = None
_session_factory = None


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = make_engine(get_config().db_url)
        _session_factory = make_session_factory(_engine)
    return _engine


def get_session():
    get_engine()
    s = _session_factory()
    try:
        yield s
    finally:
        s.close()
