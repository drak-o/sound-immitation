"""Local page for the OBS browser source."""

from __future__ import annotations

import asyncio
import email.utils
import json
import logging
import threading
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/styles.css": "styles.css",
    "/overlay.js": "overlay.js",
}

_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


class OverlayHub:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._clients: set = set()
        self._history: list[dict] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._server = None
        self._start_error: OSError | None = None

    def start(self, port: int) -> None:
        logging.getLogger("websockets.server").setLevel(logging.WARNING)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, args=(port,), name="overlay", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise SystemExit(f"Overlay did not start on port {port}.")
        if self._start_error is not None:
            raise SystemExit(
                f"Overlay did not start on port {port}: {self._start_error}"
            )

    def publish(self, message: dict) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._enqueue, message)

    def _enqueue(self, message: dict) -> None:
        self._note(message)
        asyncio.create_task(self._broadcast(json.dumps(message)))

    def _note(self, message: dict) -> None:
        """Keep the messages a late OBS source needs to draw the current frame."""
        kind = message.get("type")
        if kind == "idle":
            self._history = [message]
        elif kind == "reference":
            self._history = [message]
        elif kind == "countdown":
            self._history = [
                item for item in self._history if item.get("type") == "reference"
            ]
            self._history.append(message)
        elif kind == "recording":
            self._history = [
                item for item in self._history if item.get("type") == "reference"
            ]
            self._history.append(message)
        elif kind == "result":
            self._history = [
                item
                for item in self._history
                if item.get("type") in ("reference", "recording")
            ]
            self._history.append(message)

    async def _broadcast(self, payload: str) -> None:
        stale = []
        for client in list(self._clients):
            try:
                await client.send(payload)
            except Exception:
                stale.append(client)
        for client in stale:
            self._clients.discard(client)

    def _run(self, port: int) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start(port))
        except OSError as error:
            self._start_error = error
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()

    async def _start(self, port: int) -> None:
        self._server = await serve(
            self._handler, "127.0.0.1", port, process_request=self._http
        )

    async def _handler(self, websocket) -> None:
        try:
            for message in list(self._history):
                await websocket.send(json.dumps(message))
            self._clients.add(websocket)
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)

    def _http(self, connection, request):
        path = request.path.split("?", 1)[0]
        if path == "/ws":
            return None
        name = _FILES.get(path)
        if name is None:
            return connection.respond(404, "Not found\n")
        file_path = self._directory / name
        if not file_path.is_file():
            return connection.respond(404, "Not found\n")
        body = file_path.read_bytes()
        headers = Headers(
            [
                ("Date", email.utils.formatdate(usegmt=True)),
                ("Connection", "close"),
                ("Content-Length", str(len(body))),
                ("Content-Type", _TYPES[file_path.suffix]),
                ("Cache-Control", "no-store"),
            ]
        )
        return Response(200, "OK", headers, body)
