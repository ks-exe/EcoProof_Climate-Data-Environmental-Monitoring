"""Bounded, unambiguous JSON uploads, using FastAPI's documented custom route hook."""

from collections.abc import Awaitable, Callable
from decimal import Decimal
import json
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute


MAX_BODY_BYTES = 65536


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


class ExactJSONRequest(Request):
    async def body(self) -> bytes:
        if not hasattr(self, "_body"):
            if self.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise HTTPException(415, "Use Content-Type: application/json")
            chunks = []
            size = 0
            async for chunk in self.stream():
                size += len(chunk)
                if size > MAX_BODY_BYTES:
                    raise HTTPException(413, "JSON upload exceeds 64 KiB")
                chunks.append(chunk)
            self._body = b"".join(chunks)
        return self._body

    async def json(self) -> Any:
        if not hasattr(self, "_json"):
            try:
                self._json = json.loads((await self.body()).decode("utf-8"), parse_float=Decimal,
                                        object_pairs_hook=unique_object, parse_constant=reject_constant)
            except (ValueError, UnicodeError, RecursionError):
                raise HTTPException(422, "Upload must be valid UTF-8 JSON with unique keys and finite numbers") from None
        return self._json


class ExactJSONRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def exact_handler(request: Request) -> Response:
            return await handler(ExactJSONRequest(request.scope, request.receive))

        return exact_handler
