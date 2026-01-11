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
Middleware for request ID handling and request/response logging.

This module provides middleware that:
1. Extracts or generates request IDs for each request
2. Adds request IDs to the logging context
3. Includes request IDs in response headers
4. Logs incoming requests and outgoing responses
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings
from app.logging import get_logger, set_request_context, clear_request_context

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle request IDs and structured logging.

    This middleware:
    1. Extracts request ID from incoming request header or generates a new UUID
    2. Sets up logging context with request ID, path, and method
    3. Logs the incoming request
    4. Adds request ID to the response headers
    5. Logs the outgoing response with status code and duration
    6. Cleans up logging context after the request

    The request ID header name is configurable via REQUEST_ID_HEADER env var.
    """

    def __init__(self, app: ASGIApp):
        """
        Initialize the middleware.

        Args:
            app: The ASGI application
        """
        super().__init__(app)
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process each request and add request ID handling.

        Args:
            request: The incoming request
            call_next: Function to call the next middleware/handler

        Returns:
            The response with request ID header added
        """
        # Extract or generate request ID
        request_id = request.headers.get(
            self.settings.request_id_header.lower()
        ) or str(uuid.uuid4())

        # Set up logging context for this request
        set_request_context(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        # Log incoming request
        start_time = time.time()
        logger.info(
            "request_started",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            client_host=request.client.host if request.client else None,
        )

        try:
            # Process the request
            response = await call_next(request)

            # Calculate request duration
            duration_ms = (time.time() - start_time) * 1000

            # Add request ID to response headers
            response.headers[self.settings.request_id_header] = request_id

            # Log successful response
            logger.info(
                "request_completed",
                request_id=request_id,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            return response

        except Exception as e:
            # Calculate request duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                "request_failed",
                request_id=request_id,
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=round(duration_ms, 2),
                exc_info=True,
            )

            # Re-raise the exception to be handled by exception handlers
            raise

        finally:
            # Clean up logging context
            clear_request_context()
