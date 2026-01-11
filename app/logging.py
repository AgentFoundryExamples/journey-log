# Copyright 2025 John Brosnihan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Structured logging configuration for Cloud Logging compatibility.

This module configures structlog to emit JSON-formatted logs to stdout
with fields expected by Cloud Logging (timestamp, severity, message, etc.).
It also provides context management for request-scoped logging.
"""

import logging
import sys
from typing import Any
from contextvars import ContextVar

import structlog
from structlog.types import EventDict, Processor

from app.config import get_settings

# Context variable to store request-scoped data (request_id, path, method)
request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})


def add_request_context(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor to add request context to log entries.

    Args:
        logger: The logger instance
        method_name: The name of the method being logged
        event_dict: The event dictionary to enhance

    Returns:
        Enhanced event dictionary with request context
    """
    ctx = request_context.get()
    if ctx:
        event_dict.update(ctx)
    return event_dict


def add_environment(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Processor to add environment information to log entries.

    Args:
        logger: The logger instance
        method_name: The name of the method being logged
        event_dict: The event dictionary to enhance

    Returns:
        Enhanced event dictionary with environment info
    """
    settings = get_settings()
    event_dict["environment"] = settings.service_environment
    event_dict["service"] = settings.service_name
    return event_dict


def rename_event_key(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Rename 'event' key to 'message' for Cloud Logging compatibility.

    Cloud Logging expects the log message in a field called 'message'.

    Args:
        logger: The logger instance
        method_name: The name of the method being logged
        event_dict: The event dictionary to modify

    Returns:
        Modified event dictionary with 'message' instead of 'event'
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog for structured JSON logging.

    This function sets up structlog to emit Cloud Logging-compatible JSON logs
    to stdout. The configuration differs between development and production:

    - **Development**: More verbose logging with pretty-printed console output
    - **Production**: JSON-formatted logs with standardized fields for Cloud Logging

    The following fields are included in every log entry:
    - timestamp: ISO 8601 formatted timestamp
    - level/severity: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - message: The log message
    - environment: The service environment (dev/staging/prod)
    - service: The service name
    - request_id: Request ID (if available from context)
    - path: Request path (if available from context)
    - method: HTTP method (if available from context)

    This function should be called once at application startup.
    """
    settings = get_settings()

    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )

    # Build processor chain
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_context,
        add_environment,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # In dev mode, use prettier console output for readability
    # In production, use JSON for Cloud Logging
    if settings.service_environment == "dev":
        processors = shared_processors + [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.ExceptionRenderer(),
            rename_event_key,
            structlog.processors.JSONRenderer(),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Optional logger name. If not provided, uses the caller's module name.

    Returns:
        A structlog BoundLogger instance configured for structured logging.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("request_received", path="/health", method="GET")
    """
    return structlog.get_logger(name)


def set_request_context(request_id: str, path: str, method: str) -> None:
    """
    Set request-scoped context for logging.

    This function should be called by middleware at the start of each request
    to populate context variables that will be included in all log entries
    during that request.

    Args:
        request_id: Unique identifier for the request
        path: Request path (e.g., "/health")
        method: HTTP method (e.g., "GET")
    """
    request_context.set(
        {
            "request_id": request_id,
            "path": path,
            "method": method,
        }
    )


def clear_request_context() -> None:
    """
    Clear request-scoped context.

    This function should be called by middleware at the end of each request
    to clean up context variables.
    """
    request_context.set({})
