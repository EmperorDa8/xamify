import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app as _fastapi_app


class _StripApiPrefix:
    """Strip /api prefix from the request path before forwarding to FastAPI."""

    def __init__(self, app, prefix: str = "/api"):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path.startswith(self.prefix):
                new_path = path[len(self.prefix):] or "/"
                scope = dict(scope, path=new_path)
                raw = scope.get("raw_path", b"")
                prefix_bytes = self.prefix.encode()
                if raw.startswith(prefix_bytes):
                    scope["raw_path"] = raw[len(prefix_bytes):] or b"/"
        await self.app(scope, receive, send)


app = _StripApiPrefix(_fastapi_app)
