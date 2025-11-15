"""Logging configuration utilities."""
from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once for the entire application."""

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

