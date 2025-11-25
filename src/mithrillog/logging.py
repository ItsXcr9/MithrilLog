import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Union

import structlog
from pythonjsonlogger import jsonlogger

class LogAction(Enum):
    SUPPRESS = auto()
    ALLOW = auto()
    RECLASSIFY = auto()

@dataclass
class LogPattern:
    pattern: str
    action: LogAction
    # For RECLASSIFY:
    new_level: Optional[str] = None
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        self._compiled_pattern = re.compile(self.pattern)

    def matches(self, message: str) -> bool:
        return bool(self._compiled_pattern.search(message))

class LogProcessor:
    def __init__(self, patterns: List[LogPattern]):
        self.patterns = patterns

    def __call__(
        self, logger: logging.Logger, name: str, event_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Get the log message. structlog usually puts it in "event" or "message"
        # depending on configuration, but standard is "event".
        message = event_dict.get("event")
        if not isinstance(message, str):
            return event_dict

        for p in self.patterns:
            if p.matches(message):
                if p.action == LogAction.ALLOW:
                    # Explicitly allowed, stop processing patterns and return
                    return event_dict
                
                elif p.action == LogAction.SUPPRESS:
                    raise structlog.DropEvent
                
                elif p.action == LogAction.RECLASSIFY:
                    if p.new_level:
                        event_dict["level"] = p.new_level.lower()
                    if p.extra_fields:
                        event_dict.update(p.extra_fields)
                    # For reclassify, we might want to continue processing or stop.
                    # Let's assume we continue to allow multiple reclassifications,
                    # but if we want "first match wins" logic for everything, we'd break here.
                    # Given the requirement "no custom fields such as intentional", 
                    # it implies we might want to tag it.
                    # Let's stick to "continue" for reclassify to allow cumulative updates,
                    # but "stop" for allow/suppress.
                    pass
        
        return event_dict

def configure_logging(
    level: str = "INFO", 
    patterns: Optional[List[LogPattern]] = None
) -> None:
    """Configure structured logging for the application."""
    
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if patterns:
        # Add our custom processor before the renderer
        shared_processors.append(LogProcessor(patterns))

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
