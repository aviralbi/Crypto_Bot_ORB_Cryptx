"""
CryptX Socket.IO live tick feed (fawss.cryptxindia.com).
Listens to aggTrade events → streams (price, timestamp_IST) ticks.
Auto-reconnects on disconnect.
"""

import queue
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import pytz
import socketio

from utils import get_logger, to_ist

logger = get_logger("data_feed")

UTC = pytz.utc


# ---------------------------------------------------------------------------
# Live feed
# ---------------------------------------------------------------------------

class CryptXFeed:
    """
    Connects to CryptX FAWSS via Socket.IO and streams price ticks.

    aggTrade event format:
      {"e": "aggTrade", "E": <ms epoch>, "s": "BTCUSDT", "p": "81623.2", ...}
    """

    def __init__(
        self,
        ws_url: str,
        symbol: str,
        on_tick: Callable[[float, datetime], None],
        api_key: str = "",
        reconnect_delay: float = 5.0,
    ):
        self._url = ws_url
        self._symbol = symbol
        self._on_tick = on_tick
        self._api_key = api_key
        self._reconnect_delay = reconnect_delay
        self._running = False
        self._sio: Optional[socketio.Client] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="sio-feed")
        self._thread.start()
        logger.info("Feed starting: %s  symbol=%s", self._url, self._symbol)

    def stop(self):
        self._running = False
        if self._sio and self._sio.connected:
            self._sio.disconnect()
        logger.info("Feed stopped")

    def _run_loop(self):
        while self._running:
            try:
                self._connect()
            except Exception as exc:
                logger.warning("Feed error: %s — retry in %.0fs", exc, self._reconnect_delay)
            if self._running:
                time.sleep(self._reconnect_delay)

    def _connect(self):
        sio = socketio.Client(logger=False, engineio_logger=False)
        self._sio = sio

        @sio.on("connect")
        def _on_connect():
            sym = self._symbol.lower()
            logger.info("Socket.IO connected — subscribing %s@aggTrade", sym)
            sio.emit("subscribe", {"params": [f"{sym}@aggTrade"]})


        @sio.on("aggTrade")
        def _on_trade(data):
            try:
                price = float(data.get("p", 0))
                ts_ms  = data.get("E", 0)
                if not price or not ts_ms:
                    return
                ts = datetime.utcfromtimestamp(ts_ms / 1000).replace(tzinfo=UTC)
                self._on_tick(price, to_ist(ts))
            except Exception as exc:
                logger.debug("aggTrade parse error: %s | %s", exc, data)

        @sio.on("disconnect")
        def _on_disconnect():
            logger.info("Socket.IO disconnected")

        @sio.on("connect_error")
        def _on_error(data):
            logger.warning("Socket.IO connect error: %s", data)

        sio.connect(
            self._url,
            transports=["websocket"],
            wait_timeout=10,
        )
        sio.wait()


# ---------------------------------------------------------------------------
# Queue-based adapter (decouples feed thread from main thread)
# ---------------------------------------------------------------------------

class TickQueue:
    """
    Wraps CryptXFeed with a thread-safe queue.
    Main loop calls get() to pull ticks one at a time.
    """

    def __init__(self, ws_url: str, symbol: str, api_key: str = "", reconnect_delay: float = 5.0):
        self._q: queue.Queue = queue.Queue(maxsize=10_000)
        self._feed = CryptXFeed(ws_url, symbol, self._enqueue, api_key, reconnect_delay)

    def _enqueue(self, price: float, ts: datetime):
        try:
            self._q.put_nowait((price, ts))
        except queue.Full:
            logger.warning("Tick queue full — dropping tick price=%.2f", price)

    def start(self):
        self._feed.start()

    def stop(self):
        self._feed.stop()

    def get(self, timeout: float = 1.0) -> Optional[tuple[float, datetime]]:
        """Returns (price, ts) or None on timeout."""
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None
