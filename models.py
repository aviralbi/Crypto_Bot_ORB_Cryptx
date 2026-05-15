"""
Data structures and CandleBuilder. All shared types live here.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")

TIMEFRAME_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeState(str, Enum):
    WATCHING_ENTRY = "WATCHING_ENTRY"
    IN_TRADE = "IN_TRADE"
    CLOSED = "CLOSED"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TRAIL_STOP = "TRAIL_STOP"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MANUAL = "MANUAL"


# ---------------------------------------------------------------------------
# Candle
# ---------------------------------------------------------------------------

@dataclass
class Candle:
    timestamp: datetime   # candle open time, IST-aware
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str = "15m"

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def body_top(self) -> float:
        return max(self.open, self.close)

    @property
    def body_bottom(self) -> float:
        return min(self.open, self.close)

    @property
    def upper_wick(self) -> float:
        return self.high - self.body_top

    @property
    def lower_wick(self) -> float:
        return self.body_bottom - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    def __repr__(self):
        return f"Candle({self.timestamp.strftime('%H:%M')} O={self.open} H={self.high} L={self.low} C={self.close})"


# ---------------------------------------------------------------------------
# CandleBuilder — ticks → OHLCV bars
# ---------------------------------------------------------------------------

def _bar_open_time(ts: datetime, timeframe: str) -> datetime:
    minutes = TIMEFRAME_MINUTES[timeframe]
    ist = ts.astimezone(IST)
    total = ist.hour * 60 + ist.minute
    floored = (total // minutes) * minutes
    h, m = divmod(floored, 60)
    return ist.replace(hour=h, minute=m, second=0, microsecond=0)


class CandleBuilder:
    """
    Feed ticks via on_tick(). Returns completed Candle when bar closes.
    Call inject_historical() to pre-load candles on restart.
    """

    def __init__(self, timeframe: str = "15m"):
        if timeframe not in TIMEFRAME_MINUTES:
            raise ValueError(f"Unknown timeframe: {timeframe}")
        self.timeframe = timeframe
        self._current: Optional[Candle] = None
        self._bar_open: Optional[datetime] = None
        self._completed: list[Candle] = []

    def on_tick(self, price: float, ts: datetime, volume: float = 0.0) -> Optional[Candle]:
        bar_open = _bar_open_time(ts, self.timeframe)

        if self._current is None:
            self._open_bar(price, bar_open, volume)
            return None

        if bar_open > self._bar_open:
            closed = self._close_bar()
            self._completed.append(closed)
            self._open_bar(price, bar_open, volume)
            return closed

        self._current.high = max(self._current.high, price)
        self._current.low = min(self._current.low, price)
        self._current.close = price
        self._current.volume += volume
        return None

    def _open_bar(self, price: float, bar_open: datetime, volume: float):
        self._bar_open = bar_open
        self._current = Candle(bar_open, price, price, price, price, volume, self.timeframe)

    def _close_bar(self) -> Candle:
        c = self._current
        self._current = None
        self._bar_open = None
        return c

    @property
    def current_candle(self) -> Optional[Candle]:
        return self._current

    @property
    def completed_candles(self) -> list[Candle]:
        return list(self._completed)

    def last_n(self, n: int) -> list[Candle]:
        return self._completed[-n:]

    def inject_historical(self, candles: list[Candle]):
        self._completed.extend(candles)


# ---------------------------------------------------------------------------
# Strategy models
# ---------------------------------------------------------------------------

@dataclass
class OpeningRange:
    date: datetime
    high: float
    low: float
    formed_at: datetime
    valid_until: datetime

    @property
    def range_size(self) -> float:
        return self.high - self.low

    def is_valid(self, now: datetime) -> bool:
        return self.formed_at <= now < self.valid_until

    def __repr__(self):
        return f"OR({self.date.date()} H={self.high} L={self.low})"


@dataclass
class TriggerSetup:
    direction: Direction
    trigger_candle: Candle
    prev_candle: Candle
    orb: OpeningRange
    reference_level: float   # trigger high (long) or trigger low (short)
    sl_price: float          # prev_candle low (long) or high (short)
    detected_at: datetime


@dataclass
class Trade:
    id: str
    direction: Direction
    entry_price: float
    sl_price: float
    initial_sl: float
    quantity: float
    entry_time: datetime
    setup: TriggerSetup

    state: TradeState = TradeState.IN_TRADE
    current_target: float = 0.0
    trail_steps_hit: int = 0
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None

    ai_decision: Optional[str] = None
    ai_confidence: Optional[int] = None
    ai_reason: Optional[str] = None

    @property
    def r_size(self) -> float:
        return abs(self.entry_price - self.initial_sl)

    @property
    def pnl(self) -> Optional[float]:
        if self.exit_price is None:
            return None
        mult = 1 if self.direction == Direction.LONG else -1
        return mult * (self.exit_price - self.entry_price) * self.quantity

    @property
    def pnl_r(self) -> Optional[float]:
        if self.pnl is None or self.r_size == 0:
            return None
        return self.pnl / (self.r_size * self.quantity)


@dataclass
class DailyState:
    date: datetime
    long_entries: int = 0
    short_entries: int = 0
    realized_pnl: float = 0.0
    trading_halted: bool = False
    active_trade: Optional[Trade] = None
    orb: Optional[OpeningRange] = None

    def can_trade_long(self, max_long: int) -> bool:
        return not self.trading_halted and self.long_entries < max_long

    def can_trade_short(self, max_short: int) -> bool:
        return not self.trading_halted and self.short_entries < max_short
