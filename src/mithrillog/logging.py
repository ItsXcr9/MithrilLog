import logging
import sys
from typing import Any

import structlog
from pythonjsonlogger import jsonlogger

def configure_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    handler = logging.StreamHandler(sys.stdout)
    
    # Use python-json-logger for the standard library handler to ensure
    # third-party libs (like uvicorn) also output JSON if possible,
    # or at least formatted correctly.
    # However, for simplicity and consistency with structlog, we'll just
    # let structlog handle its own output and redirect stdlib to it if needed.
    # But a simpler approach for mixed environments is to just format everything as JSON.
    
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
    
    # Silence noisy libraries
    logging.getLogger("uvicorn.access").handlers = []  # Let uvicorn use root handler
    logging.getLogger("uvicorn.error").handlers = []
