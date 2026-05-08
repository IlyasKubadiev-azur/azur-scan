"""Rotating-file + console logger setup."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOG_FILE, LOG_DIR

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure(level: str = "INFO") -> None:
    level_value = getattr(logging, level.upper(), logging.INFO)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(
            LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8",
        ),
    ]
    formatter = logging.Formatter(_LOG_FORMAT)
    for h in handlers:
        h.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level_value)
    root.handlers = handlers

    # Quiet down noisy 3rd-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
