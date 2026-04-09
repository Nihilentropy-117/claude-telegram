"""Logging configuration."""

from __future__ import annotations

import logging


def configure_logging(level_name: str) -> None:
    """Configure application-wide logging."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

