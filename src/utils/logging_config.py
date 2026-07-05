"""
Centralised logging configuration for the CRM Meeting Assistant.

Call `get_logger(__name__)` at the top of every module to get a consistent,
project-wide logger instead of using bare `print()` statements.
"""
import logging
import os

# ---------------------------------------------------------------------------
# Log level — controlled via environment variable, defaults to INFO
# ---------------------------------------------------------------------------
_LEVEL_NAME: str = os.environ.get("CRM_LOG_LEVEL", "INFO").upper()
_LOG_LEVEL: int = getattr(logging, _LEVEL_NAME, logging.INFO)

# ---------------------------------------------------------------------------
# Root logger setup (called once on import)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Silence noisy third-party loggers that are not useful during normal runs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("google.auth").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger for the given module.

    Usage::

        from src.utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Starting up")
    """
    return logging.getLogger(name)
