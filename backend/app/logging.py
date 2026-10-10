import logging
import os
import sys

import structlog


def _stream():
    """stdout saat ini. Di `pythonw.exe` (peluncur Windows tanpa konsol) sys.stdout bisa None."""
    return sys.stdout if sys.stdout is not None else open(os.devnull, "w", encoding="utf-8")


def setup_logging(level: str = "INFO") -> None:
    stream = _stream()
    logging.basicConfig(format="%(message)s", stream=stream, level=level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        # structlog menangkap sys.stdout saat modulnya DI-IMPOR (bukan saat dipakai). Beri file eksplisit agar
        # pengalihan stdout yang dilakukan kemudian (peluncur Windows) ikut berlaku.
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
