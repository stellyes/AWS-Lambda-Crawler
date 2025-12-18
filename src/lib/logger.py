"""
Structured JSON logger for AWS Lambda
Outputs JSON for easy CloudWatch parsing and filtering
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Optional


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for CloudWatch"""

    def __init__(self, context: Optional[dict[str, Any]] = None):
        super().__init__()
        self.context = context or {}

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            **self.context,
        }

        # Add extra fields from the record
        if hasattr(record, "extra"):
            log_entry.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class ContextLogger:
    """Logger that supports adding context to all messages"""

    def __init__(
        self,
        name: str = "crawler",
        level: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        self.name = name
        self.context = context or {}
        self.level = self._get_level(level)
        self._logger = self._setup_logger()

    def _get_level(self, level: Optional[str]) -> int:
        """Get logging level from string or environment"""
        level_str = level or os.environ.get("LOG_LEVEL", "INFO")
        return getattr(logging, level_str.upper(), logging.INFO)

    def _setup_logger(self) -> logging.Logger:
        """Set up the logger with JSON formatting"""
        logger = logging.getLogger(self.name)
        logger.setLevel(self.level)

        # Remove existing handlers
        logger.handlers.clear()

        # Add JSON handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(self.context))
        logger.addHandler(handler)

        # Prevent propagation to root logger
        logger.propagate = False

        return logger

    def with_context(self, **kwargs: Any) -> "ContextLogger":
        """Create a new logger with additional context"""
        new_context = {**self.context, **kwargs}
        return ContextLogger(
            name=self.name,
            level=logging.getLevelName(self.level),
            context=new_context,
        )

    def _log(
        self, level: int, message: str, extra: Optional[dict[str, Any]] = None
    ) -> None:
        """Internal log method that adds extra context"""
        record_extra = {**self.context}
        if extra:
            record_extra.update(extra)

        # Create a log record with extra data
        self._logger.log(
            level,
            message,
            extra={"extra": record_extra} if record_extra else {},
        )

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message"""
        self._log(logging.DEBUG, message, kwargs if kwargs else None)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message"""
        self._log(logging.INFO, message, kwargs if kwargs else None)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message"""
        self._log(logging.WARNING, message, kwargs if kwargs else None)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message"""
        self._log(logging.ERROR, message, kwargs if kwargs else None)

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log an exception with traceback"""
        self._logger.exception(
            message,
            extra={"extra": {**self.context, **kwargs}} if kwargs else {"extra": self.context},
        )


def get_logger(
    name: str = "crawler",
    level: Optional[str] = None,
    **context: Any,
) -> ContextLogger:
    """Create a new logger instance"""
    return ContextLogger(name=name, level=level, context=context)
