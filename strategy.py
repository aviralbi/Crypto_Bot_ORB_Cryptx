"""
Strategy core: ORB calculator, trigger detection, entry watching, SL/trail, position sizing.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from models import (
    Candle, OpeningRange, TriggerSetup, Trade,
    Direction, TradeState, ExitReason,
)
from utils import make_ist_time, get_logger, IST, round_qty

logger = get_logger("strategy")


# ---------------------------------------------------------------------------
# 1. ORB Calculator
# ---------------------------------------------------------------------------

class ORBCalculator:
    """
    Accumulates 15m candles during the 5:30–9:30 AM IST OR window.
    Finalizes OpeningRange on the last candle of the window (9:15 close).
    Resets automatically when a new day's OR window begins.
    """

    def __init__(self, or_start: str = "05:30", or_end: str = "09:30", tf_minutes: int = 15):
        self._or_start = or_start
        self._or_end = or_end
        self._tf_min = tf_minutes
        self._high = float("-inf")
        self._low = float("inf")
        self._accumulating = False
        self._finalized = False
        self._or_date = None
        self._current_or: Optional[OpeningRange] = None

    def on_candle(self, candle: Candle) -> Optional[OpeningRange]:
        """Feed each closed candle. Returns OpeningRange when OR finalizes, else None."""
        ts = candle.timestamp.astimezone(IST)
        today = ts.date()
        or_start = make_ist_time(self._or_start, ts)
        or_end = make_ist_time(self._or_end, ts)

        # New trading day → reset
        if self._or_date is not None and today != self._or_date:
            logger.info("New day %s — OR reset", today)
            self._reset()

        # Start accumulating when first OR-window candle arrives
        if not self._accumulating and not self._finalized and ts >= or_start:
            self._accumulating = True
            self._or_date = today
            logger.info("OR accumulation started %s", today)

        if self._accumulating and or_start <= ts < or_end:
            self._high = max(self._high, candle.high)
            self._low = min(self._low, candle.low)
            # Last candle in window: next bar opens at or_end
            if ts + timedelta(minutes=self._tf_min) >= or_end:
                return self._finalize(ts)

        return None

    def _finalize(self, ts: datetime) -> OpeningRange:
        self._accumulating = False
        self._finalized = True
        formed_at = make_ist_time(self._or_end, ts)
        valid_until = make_ist_time(self._or_start, ts + timedelta(days=1))
        orb = OpeningRange(
            date=ts,
            high=self._high,
            low=self._low,
            formed_at=formed_at,
            valid_until=valid_until,
        )
        self._current_or = orb
        logger.info("OR finalized: H=%.2f L=%.2f", orb.high, orb.low)
        return orb

    def _reset(self):
        self._high = float("-inf")
        self._low = float("inf")
        self._accumulating = False
        self._finalized = False
        self._or_date = None
        self._current_or = None

    @property
    def current_or(self) -> Optional[OpeningRange]:
        return self._current_or


# ---------------------------------------------------------------------------
# 2. Trigger Detector
# ---------------------------------------------------------------------------

class TriggerDetector:
    """
    Evaluates each closed 15m candle for ORB trigger conditions.
    Long: close > OR High, ≥ body_threshold% of body above OR High.
    Short: close < OR Low,  ≥ body_threshold% of body below OR Low.
    Returns list so both directions can trigger independently per candle.
    """

    def __init__(self, body_threshold_pct: float = 60):
        self._threshold = body_threshold_pct / 100.0

    def check(self, candle: Candle, prev_candle: Candle, orb: OpeningRange) -> list[TriggerSetup]:
        """
        prev_candle: candle immediately BEFORE trigger candle (source of SL price).
        Only evaluates candles after OR validity begins (>= 9:30 AM IST).
        """
        if not orb.is_valid(candle.timestamp):
            return []

        triggers = []

        if self._is_long_trigger(candle, orb):
            setup = TriggerSetup(
                direction=Direction.LONG,
                trigger_candle=candle,
                prev_candle=prev_candle,
                orb=orb,
                reference_level=candle.high,   # entry breaks above trigger HIGH
                sl_price=prev_candle.low,       # SL at low of candle BEFORE trigger
                detected_at=candle.timestamp,
            )
            triggers.append(setup)
            logger.info("LONG trigger: ref=%.2f sl=%.2f", setup.reference_level, setup.sl_price)

        if self._is_short_trigger(candle, orb):
            setup = TriggerSetup(
                direction=Direction.SHORT,
                trigger_candle=candle,
                prev_candle=prev_candle,
                orb=orb,
                reference_level=candle.low,    # entry breaks below trigger LOW
                sl_price=prev_candle.high,      # SL at high of candle BEFORE trigger
                detected_at=candle.timestamp,
            )
            triggers.append(setup)
            logger.info("SHORT trigger: ref=%.2f sl=%.2f", setup.reference_level, setup.sl_price)

        return triggers

    def _is_long_trigger(self, candle: Candle, orb: OpeningRange) -> bool:
        if candle.close <= orb.high or candle.body == 0:
            return False
        # Portion of body above OR High
        portion_above = candle.body_top - max(candle.body_bottom, orb.high)
        return portion_above >= self._threshold * candle.body

    def _is_short_trigger(self, candle: Candle, orb: OpeningRange) -> bool:
        if candle.close >= orb.low or candle.body == 0:
            return False
        # Portion of body below OR Low
        portion_below = min(candle.body_top, orb.low) - candle.body_bottom
        return portion_below >= self._threshold * candle.body


# ---------------------------------------------------------------------------
# 3. Entry Watcher
# ---------------------------------------------------------------------------

class EntryWatcher:
    """
    Armed with a TriggerSetup, monitors the NEXT 15m candle for a tick break.

    States: IDLE → ARMED (trigger confirmed) → WATCHING (on entry candle) → IDLE

    Call on_tick(price, current_bar_open) every tick.
    Returns (entry_price, invalidated):
      - entry_price is not None → enter trade at that price
      - invalidated is True     → trigger expired, no entry

    Create two instances (long_watcher, short_watcher) for independent direction scanning.
    """

    def __init__(self):
        self._trigger: Optional[TriggerSetup] = None
        self._trigger_bar_open: Optional[datetime] = None
        self._entry_bar_open: Optional[datetime] = None
        self._state = "IDLE"
        self._first_tick = False

    def arm(self, trigger: TriggerSetup, trigger_bar_open: datetime):
        """Call when trigger candle is confirmed (at candle close)."""
        self._trigger = trigger
        self._trigger_bar_open = trigger_bar_open
        self._entry_bar_open = None
        self._state = "ARMED"
        self._first_tick = False
        logger.info(
            "EntryWatcher ARMED %s ref=%.2f sl=%.2f",
            trigger.direction.value, trigger.reference_level, trigger.sl_price
        )

    def reset(self):
        self._trigger = None
        self._trigger_bar_open = None
        self._entry_bar_open = None
        self._state = "IDLE"
        self._first_tick = False

    @property
    def is_active(self) -> bool:
        return self._state in ("ARMED", "WATCHING")

    @property
    def active_trigger(self) -> Optional[TriggerSetup]:
        return self._trigger if self.is_active else None

    def on_tick(self, price: float, current_bar_open: datetime) -> tuple[Optional[float], bool]:
        if self._state == "IDLE":
            return None, False

        if self._state == "ARMED":
            if current_bar_open > self._trigger_bar_open:
                # First tick of entry candle
                self._state = "WATCHING"
                self._entry_bar_open = current_bar_open
                self._first_tick = True
                logger.info("Entry candle opened %s", current_bar_open.strftime("%H:%M"))
            else:
                return None, False  # still ticking on trigger candle

        # WATCHING
        if current_bar_open > self._entry_bar_open:
            # Entry candle fully closed without a break → invalidate
            logger.info("Trigger invalidated — entry candle closed without break")
            self.reset()
            return None, True

        direction = self._trigger.direction
        ref = self._trigger.reference_level

        if self._first_tick:
            self._first_tick = False
            # Gap scenario: entry candle opened beyond reference level
            if direction == Direction.LONG and price > ref:
                logger.info("Gap-up entry at open=%.2f (ref=%.2f)", price, ref)
                self.reset()
                return price, False
            if direction == Direction.SHORT and price < ref:
                logger.info("Gap-down entry at open=%.2f (ref=%.2f)", price, ref)
                self.reset()
                return price, False

        # Tick break
        if direction == Direction.LONG and price > ref:
            logger.info("LONG entry: tick=%.2f > ref=%.2f", price, ref)
            self.reset()
            return price, False
        if direction == Direction.SHORT and price < ref:
            logger.info("SHORT entry: tick=%.2f < ref=%.2f", price, ref)
            self.reset()
            return price, False

        return None, False


# ---------------------------------------------------------------------------
# 4. SL / Trail Manager
# ---------------------------------------------------------------------------

class SLTrailManager:
    """
    Manages stop loss and step-up trailing for an active trade.

    Trail schedule (configurable initial_rr and trail_step):
      Step 0: target at 1:2 → when hit, SL moves to 1:2 level, target becomes 1:3
      Step 1: target at 1:3 → when hit, SL moves to 1:3 level, target becomes 1:4
      ...continues indefinitely until SL is touched

    Call on_tick() with every live price. Returns action + value.
    """

    def __init__(self):
        self._trade: Optional[Trade] = None
        self._next_r = 0.0
        self._trail_step = 1.0

    def setup(self, trade: Trade, initial_rr: float, trail_step: float = 1.0):
        """Call immediately after trade entry. Sets first target on the trade object."""
        self._trade = trade
        self._next_r = initial_rr
        self._trail_step = trail_step

        if trade.direction == Direction.LONG:
            trade.current_target = trade.entry_price + self._next_r * trade.r_size
        else:
            trade.current_target = trade.entry_price - self._next_r * trade.r_size

        logger.info(
            "SL manager: %s entry=%.2f sl=%.2f R=%.2f target=%.2f (1:%.0f)",
            trade.direction.value, trade.entry_price, trade.sl_price,
            trade.r_size, trade.current_target, self._next_r
        )

    def on_tick(self, price: float) -> tuple[str, Optional[float]]:
        """
        Returns:
          ("exit",  price)   — SL hit, exit trade
          ("trail", new_sl)  — target hit, SL stepped up
          ("none",  None)    — nothing to do
        """
        if self._trade is None:
            return "none", None

        t = self._trade

        if t.direction == Direction.LONG:
            if price <= t.sl_price:
                logger.info("SL hit (long): price=%.2f sl=%.2f", price, t.sl_price)
                return "exit", price
            if price >= t.current_target:
                return self._step_trail()
        else:
            if price >= t.sl_price:
                logger.info("SL hit (short): price=%.2f sl=%.2f", price, t.sl_price)
                return "exit", price
            if price <= t.current_target:
                return self._step_trail()

        return "none", None

    def _step_trail(self) -> tuple[str, float]:
        t = self._trade
        new_sl = t.current_target   # SL locks at the level that was just hit
        old_target = t.current_target
        t.sl_price = new_sl
        t.trail_steps_hit += 1
        self._next_r += self._trail_step

        if t.direction == Direction.LONG:
            t.current_target = t.entry_price + self._next_r * t.r_size
        else:
            t.current_target = t.entry_price - self._next_r * t.r_size

        logger.info(
            "Trail step %d: sl moved to %.2f, next target %.2f (1:%.0f)",
            t.trail_steps_hit, new_sl, t.current_target, self._next_r
        )
        return "trail", new_sl

    def reset(self):
        self._trade = None
        self._next_r = 0.0


# ---------------------------------------------------------------------------
# 5. Position Sizer
# ---------------------------------------------------------------------------

def calculate_position(entry: float, sl: float, cfg) -> float:
    """
    Returns BTC quantity (floored to min lot size).
    Returns 0.0 if trade is invalid.

    Formula:
      risk_amount = capital × risk_pct
      sl_distance = |entry − sl|
      qty = risk_amount / sl_distance   (floored to lot precision)
    """
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        logger.error("SL distance zero — cannot size position")
        return 0.0

    risk_amount = cfg.capital * (cfg.risk_per_trade_pct / 100)
    qty = risk_amount / sl_distance
    qty = round_qty(qty, cfg.quantity_decimals)

    notional = qty * entry
    margin = notional / cfg.leverage

    if qty < cfg.min_lot_size:
        logger.warning("qty %.6f < min_lot %.3f — trade rejected", qty, cfg.min_lot_size)
        return 0.0
    if margin > cfg.capital:
        logger.warning("margin ₹%.2f > capital ₹%.2f — trade rejected", margin, cfg.capital)
        return 0.0

    logger.info(
        "Position: qty=%.4f BTC | risk=₹%.0f | notional=₹%.0f | margin=₹%.0f",
        qty, risk_amount, notional, margin
    )
    return qty


# ---------------------------------------------------------------------------
# 6. Trade factory
# ---------------------------------------------------------------------------

def create_trade(trigger: TriggerSetup, entry_price: float, qty: float) -> Trade:
    return Trade(
        id=str(uuid.uuid4())[:8],
        direction=trigger.direction,
        entry_price=entry_price,
        sl_price=trigger.sl_price,
        initial_sl=trigger.sl_price,
        quantity=qty,
        entry_time=datetime.now(IST),
        setup=trigger,
    )
