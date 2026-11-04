"""Local page for the OBS browser source."""

from __future__ import annotations

import asyncio
import json
import socket
import threading

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.config import ROOT


class _NoStoreFiles(StaticFiles):
    """Hot reload support for the overlay."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


class OverlayHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    def start(self, port: int) -> None:
        try:
            sock = socket.create_server(("127.0.0.1", port))
        except OSError as error:
            raise SystemExit(f"Overlay did not start on port {port}: {error}") from None
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @app.websocket("/ws")
        async def browser(websocket: WebSocket) -> None:
            await websocket.accept()
            self._clients.add(websocket)
            try:
                # The page never sends a frame. The read ends when the browser disconnects.
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        app.mount(
            "/", _NoStoreFiles(directory=ROOT / "overlay", html=True), name="overlay"
        )
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, args=(sock,), name="overlay", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Close the page and the socket. Called when main.py exits."""
        server = self._server
        thread = self._thread
        if server is None or thread is None or not thread.is_alive():
            return
        server.should_exit = True
        thread.join(timeout=5)

    def publish(self, message: dict) -> None:
        loop = self._loop
        if loop is None:
            return
        payload = json.dumps(message)

        async def send() -> None:
            stale = []
            for client in list(self._clients):
                try:
                    await client.send_text(payload)
                except Exception:
                    stale.append(client)
            for client in stale:
                self._clients.discard(client)

        loop.call_soon_threadsafe(lambda: asyncio.create_task(send()))

    def _run(self, sock: socket.socket) -> None:
        server = self._server
        loop = self._loop
        assert server is not None and loop is not None
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve(sockets=[sock]))
