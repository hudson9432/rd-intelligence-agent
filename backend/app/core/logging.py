"""Logging setup that deliberately avoids serializing application settings."""

import logging


def configure_logging(log_level: str) -> None:
    """Configure a concise process-wide log format."""

    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
