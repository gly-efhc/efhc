from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'none'; base-uri 'none'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    ),
}


class SecurityHeadersMiddleware:
    """Добавить security headers и ограничить суммарный размер HTTP body.

    Лимит проверяется по фактическому ASGI-потоку тела, а не только по
    недоверенному ``Content-Length``. Приложение ниже по цепочке не получает
    тело сверх заданного лимита, включая chunked/streamed запросы.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        environment: str = "local",
        max_request_body_bytes: int = 1_048_576,
    ) -> None:
        self.app = app
        self.environment = str(environment or "local").lower()
        self.max_request_body_bytes = max(1, int(max_request_body_bytes))

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        content_length = request_headers.get("content-length", "").strip()
        if content_length:
            try:
                declared_body_bytes = int(content_length)
            except ValueError:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    detail="Invalid Content-Length header.",
                )
                return
            if declared_body_bytes < 0:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    detail="Invalid Content-Length header.",
                )
                return
            if declared_body_bytes > self.max_request_body_bytes:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    detail="Request body is too large.",
                )
                return

        # Буферизация до лимита не позволяет downstream начать обработку
        # частичного oversized body до того, как сервер вернёт 413.
        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            total += len(message.get("body", b""))
            if total > self.max_request_body_bytes:
                await self._send_error(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    detail="Request body is too large.",
                )
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return await receive()

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._apply_headers(scope, message)
            await send(message)

        await self.app(scope, replay_receive, secure_send)

    def _apply_headers(self, scope: Scope, message: Message) -> None:
        headers = MutableHeaders(scope=message)
        for key, value in _SECURITY_HEADERS.items():
            if key not in headers:
                headers[key] = value
        if (
            self.environment in {"prod", "stage", "staging"}
            and "Strict-Transport-Security" not in headers
        ):
            headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        path = str(scope.get("path") or "/")
        if (
            path.startswith(("/api", "/meta", "/health"))
            and "Cache-Control" not in headers
        ):
            headers["Cache-Control"] = "no-store"

    async def _send_error(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
        )

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._apply_headers(scope, message)
            await send(message)

        await response(scope, receive, secure_send)
