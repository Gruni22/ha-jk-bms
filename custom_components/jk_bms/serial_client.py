"""Async serial client for JK BMS.

Verwendet pyserial-asyncio. Hält genau einen offenen Port, serialisiert
Anfragen, und liefert das nächste vollständige Frame zurück. Robust gegen
Müll auf der Leitung (Parser puffert/resync't).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable

import serial_asyncio

from .protocol import (
    FrameParser,
    JkFrame,
    build_authenticate_frame,
    build_read_all_frame,
    build_set_register_frame,
    build_switch_frame,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 3.0  # Sekunden auf eine Antwort


class JkSerialClient:
    """Serieller Treiber für JK BMS."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._parser = FrameParser()

    # --------------------------------------------------------------------- #
    # Lifecycle
    # --------------------------------------------------------------------- #
    async def connect(self) -> None:
        if self._writer is not None:
            return
        _LOGGER.debug("Opening serial port %s @ %d", self._port, self._baudrate)
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self._port, baudrate=self._baudrate
        )

    async def disconnect(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None

    # --------------------------------------------------------------------- #
    # Send/Receive
    # --------------------------------------------------------------------- #
    async def _send_and_read(self, frame: bytes) -> JkFrame:
        await self.connect()
        assert self._reader is not None and self._writer is not None

        self._writer.write(frame)
        await self._writer.drain()

        # Lies bis Parser ein vollständiges Frame liefert oder Timeout.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("No JK frame within timeout")

            try:
                chunk = await asyncio.wait_for(
                    self._reader.read(256), timeout=remaining
                )
            except asyncio.TimeoutError as err:
                raise asyncio.TimeoutError("Serial read timeout") from err

            if not chunk:
                # Verbindung weg
                raise ConnectionError("Serial connection closed")

            self._parser.feed(chunk)
            frame_obj = self._parser.pop()
            if frame_obj is not None:
                return frame_obj

    async def read_all(self) -> JkFrame:
        async with self._lock:
            return await self._send_and_read(build_read_all_frame())

    async def set_switch(self, name: str, on: bool) -> None:
        async with self._lock:
            await self._authenticate_locked()
            await self._send_and_forget(build_switch_frame(name, on))

    async def write_register(self, address: int, value: int, width: int = 1) -> None:
        async with self._lock:
            await self._authenticate_locked()
            await self._send_and_forget(
                build_set_register_frame(address, value, width=width)
            )

    # --------------------------------------------------------------------- #
    # internals
    # --------------------------------------------------------------------- #
    async def _authenticate_locked(self) -> None:
        await self.connect()
        assert self._writer is not None
        self._writer.write(build_authenticate_frame())
        await self._writer.drain()
        # Kurze Pause, syssi setzt 150ms
        await asyncio.sleep(0.15)

    async def _send_and_forget(self, frame: bytes) -> None:
        assert self._writer is not None
        self._writer.write(frame)
        await self._writer.drain()
        # Antwort einlesen, aber nicht zurückgeben — nur Parser füttern
        try:
            await asyncio.wait_for(self._drain_some(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

    async def _drain_some(self) -> None:
        assert self._reader is not None
        chunk = await self._reader.read(256)
        if chunk:
            self._parser.feed(chunk)
            # Frames stillschweigend verwerfen
            while self._parser.pop() is not None:
                pass
