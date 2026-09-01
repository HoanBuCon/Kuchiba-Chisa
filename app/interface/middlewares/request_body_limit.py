"""ASGI request-size admission control before JSON parsing or base64 decoding."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config.settings import settings


class _RequestBodyTooLargeError(Exception):
    """Raised internally when streamed body bytes exceed the configured quota."""


class RequestBodyLimitMiddleware:
    """Enforce the aggregate API body quota for declared and chunked requests."""

    API_PREFIX = "/api/v1/"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.API_PREFIX):
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > settings.API_MAX_REQUEST_BODY_BYTES:
                    await self._send_error(scope, receive, send, "Request body too large")
                    return
            except ValueError:
                await self._send_error(scope, receive, send, "Invalid request body length", 400)
                return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > settings.API_MAX_REQUEST_BODY_BYTES:
                    raise _RequestBodyTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLargeError:
            if not response_started:
                await self._send_error(scope, receive, send, "Request body too large")

    @staticmethod
    async def _send_error(
        scope: Scope,
        receive: Receive,
        send: Send,
        detail: str,
        status_code: int = 413,
    ) -> None:
        response = JSONResponse(status_code=status_code, content={"detail": detail})
        await response(scope, receive, send)
