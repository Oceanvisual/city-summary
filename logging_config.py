"""Настройка structlog: логи в stderr (stdout занят сводкой), run_id из contextvars."""

import logging
import sys

import structlog


def configure_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
