"""structlog 기반 구조화 로깅 설정."""

from __future__ import annotations

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    """structlog + stdlib 로깅 통합 설정. JSON 라인으로 stdout 출력."""
    log_level = getattr(logging, level.upper())

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )
