"""
BTC ORB Bot — main entry point.

Run:  python main.py
Stop: Ctrl+C
"""

import json
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from utils import bootstrap, now_ist, make_ist_time, IST, get_logger
from models import (
    Candle, CandleBuilder, OpeningRange, TriggerSetup, Trade,
    DailyState, Direction, TradeState, ExitReason,
)
from strategy import (
    ORBCalculator, TriggerDetector, EntryWatcher,
    SLTrailManager, calculate_position, create_trade,
)
from ai_filter import run_ai_filter
from execution import TelegramNotifier, TradeLogger, place_entry, place_exit
from data_feed import TickQueue

logger = get_logger("main")


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _save_state(state_file: str, daily: DailyState, active_trade: Optional[Trade]):
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    orb_data = None
    if daily.orb:
        orb = daily.orb
        orb_data = {
            "high":       orb.high,
            "low":        orb.low,
            "formed_at":  orb.formed_at.isoformat(),
            "valid_until": orb.valid_until.isoformat(),
            "date":       orb.date.isoformat(),
        }

    trade_data = None
    if active_trade:
        t = active_trade
        trade_data = {
            "id":              t.id,
            "direction":       t.direction.value,
            "entry_price":     t.entry_price,
            "sl_price":        t.sl_price,
            "initial_sl":      t.initial_sl,
            "current_target":  t.current_target,
            "quantity":        t.quantity,
            "entry_time":      t.entry_time.isoformat(),
            "trail_steps_hit": t.trail_steps_hit,
            "ai_decision":     t.ai_decision,
            "ai_confidence":   t.ai_confidence,
            "ai_reason":       t.ai_reason,
        }

    payload = {
        "date":           daily.date.isoformat(),
        "long_entries":   daily.long_entries,
        "short_entries":  daily.short_entries,
        "realized_pnl":   daily.realized_pnl,
        "trading_halted": daily.trading_halted,
        "orb":            orb_data,
        "active_trade":   trade_data,
    }

    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.debug("State saved → %s", path)


def _load_state(state_file: str) -> Optional[dict]:
    path = Path(state_file)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Could not load state: %s", exc)
        return None


def _parse_orb(data: dict) -> OpeningRange:
    return OpeningRange(
        date=datetime.fromisoformat(data["date"]),
        high=data["high"],
        low=data["low"],
        formed_at=datetime.fromisoformat(data["formed_at"]),
        valid_until=datetime.fromisoformat(data["valid_until"]),
    )


def _parse_trade(data: dict) -> Trade:
    """Reconstruct Trade from saved state. setup field is None (not needed post-entry)."""
    direction = Direction(data["direction"])

    class _FakeSetup:
        pass

    fake_setup = _FakeSetup()
    trade = Trade(
        id=data["id"],
        direction=direction,
        entry_price=data["entry_price"],
        sl_price=data["sl_price"],
        initial_sl=data["initial_sl"],
        quantity=data["quantity"],
        entry_time=datetime.fromisoformat(data["entry_time"]),
        setup=fake_setup,  # type: ignore — only used at entry, not needed now
        current_target=data["current_target"],
        trail_steps_hit=data["trail_steps_hit"],
        ai_decision=data.get("ai_decision"),
        ai_confidence=data.get("ai_confidence"),
        ai_reason=data.get("ai_reason"),
    )
    return trade


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

class ORBBot:
    def __init__(self, cfg):
        self._cfg = cfg

        # Components
        self._orb_calc   = ORBCalculator(cfg.or_start_time, cfg.or_end_time, 15)
        self._trig_det   = TriggerDetector(cfg.body_threshold_pct)
        self._long_watch = EntryWatcher()
        self._short_watch = EntryWatcher()
        self._sl_mgr     = SLTrailManager()
        self._candles    = CandleBuilder("15m")
        self._notifier   = TelegramNotifier(cfg)
        self._trade_log  = TradeLogger(cfg.get("log_dir_trades", "./logs/trades"))

        # State
        self._daily  = DailyState(date=now_ist())
        self._active_trade: Optional[Trade] = None
        self._running = False

        self._restore_state()

    # -----------------------------------------------------------------------
    # State management
    # -----------------------------------------------------------------------

    def _restore_state(self):
        data = _load_state(self._cfg.state_file)
        if not data:
            logger.info("No saved state — starting fresh")
            return

        saved_date_str = data.get("date", "")
        try:
            saved_date = datetime.fromisoformat(saved_date_str)
        except Exception:
            return

        today = now_ist().date()
        is_same_day = saved_date.date() == today

        if is_same_day:
            self._daily.long_entries  = data.get("long_entries", 0)
            self._daily.short_entries = data.get("short_entries", 0)
            self._daily.realized_pnl  = data.get("realized_pnl", 0.0)
            self._daily.trading_halted = data.get("trading_halted", False)
            logger.info(
                "Restored same-day state: long=%d short=%d pnl=%.2f halted=%s",
                self._daily.long_entries, self._daily.short_entries,
                self._daily.realized_pnl, self._daily.trading_halted
            )

        orb_data = data.get("orb")
        if orb_data:
            orb = _parse_orb(orb_data)
            if orb.is_valid(now_ist()):
                self._daily.orb = orb
                self._orb_calc._current_or = orb
                logger.info("Restored OR: H=%.2f L=%.2f", orb.high, orb.low)

        trade_data = data.get("active_trade")
        if trade_data:
            trade = _parse_trade(trade_data)
            # Carry-over rule: if new day AND carry_over_blocks_new_entry,
            # keep trade active but block new entries (handled in _process_trigger)
            self._active_trade = trade
            self._daily.active_trade = trade
            # Restore SL trail manager
            next_r = self._cfg.initial_rr + trade.trail_steps_hit * self._cfg.trail_step
            self._sl_mgr._trade = trade
            self._sl_mgr._next_r = next_r
            self._sl_mgr._trail_step = self._cfg.trail_step
            logger.info(
                "Restored active trade: %s entry=%.2f sl=%.2f next_r=%.1f",
                trade.direction.value, trade.entry_price, trade.sl_price, next_r
            )

    def _save(self):
        _save_state(self._cfg.state_file, self._daily, self._active_trade)

    # -----------------------------------------------------------------------
    # Daily reset
    # -----------------------------------------------------------------------

    def _check_daily_reset(self):
        """Reset daily counters if new calendar day and we're past OR window start."""
        today = now_ist().date()
        if self._daily.date.date() == today:
            return

        logger.info("New day %s — resetting daily state", today)

        # Carry-over: if active trade from previous day, keep it
        carry_trade = self._active_trade

        self._daily = DailyState(date=now_ist())
        self._daily.active_trade = carry_trade
        if carry_trade:
            self._active_trade = carry_trade
            logger.info("Carry-over trade: %s", carry_trade.id)

        self._long_watch.reset()
        self._short_watch.reset()
        self._save()

    # -----------------------------------------------------------------------
    # Tick processing (called for every WebSocket tick)
    # -----------------------------------------------------------------------

    def process_tick(self, price: float, ts: datetime):
        self._check_daily_reset()

        # Build candle
        closed = self._candles.on_tick(price, ts)
        if closed:
            self._on_candle_close(closed)

        current_bar = (
            self._candles.current_candle.timestamp
            if self._candles.current_candle else ts
        )

        # Entry watching (tick level) — only if no active trade
        if not self._active_trade:
            for watcher in [self._long_watch, self._short_watch]:
                if not watcher.is_active:
                    continue
                entry_price, invalidated = watcher.on_tick(price, current_bar)
                if invalidated:
                    logger.info("%s trigger invalidated", watcher.active_trigger.direction.value if watcher.active_trigger else "?")
                if entry_price is not None:
                    self._execute_entry(watcher._trigger, entry_price)  # noqa
                    break  # one entry at a time

        # SL / trail monitoring (tick level)
        if self._active_trade:
            action, val = self._sl_mgr.on_tick(price)
            if action == "trail":
                self._on_trail()
            elif action == "exit":
                self._on_exit(val)

    # -----------------------------------------------------------------------
    # Candle close handler
    # -----------------------------------------------------------------------

    def _on_candle_close(self, candle: Candle):
        # OR formation
        orb = self._orb_calc.on_candle(candle)
        if orb:
            self._daily.orb = orb
            self._notifier.or_formed(orb)
            self._save()
            logger.info("OR formed: H=%.2f L=%.2f", orb.high, orb.low)

        # Trigger detection
        if not self._daily.orb:
            return
        if self._active_trade:
            return  # in trade — no new triggers

        history = self._candles.completed_candles
        if len(history) < 2:
            return
        prev = history[-2]

        triggers = self._trig_det.check(candle, prev, self._daily.orb)
        for trigger in triggers:
            self._process_trigger(trigger, candle)

    # -----------------------------------------------------------------------
    # Trigger processing
    # -----------------------------------------------------------------------

    def _process_trigger(self, trigger: TriggerSetup, trigger_candle: Candle):
        cfg = self._cfg

        # Direction limits
        if trigger.direction == Direction.LONG:
            if not self._daily.can_trade_long(cfg.max_long_entries_per_day):
                logger.info("Long limit reached — skipping")
                return
            watcher = self._long_watch
        else:
            if not self._daily.can_trade_short(cfg.max_short_entries_per_day):
                logger.info("Short limit reached — skipping")
                return
            watcher = self._short_watch

        # Halted
        if self._daily.trading_halted:
            logger.info("Trading halted — skipping trigger")
            return

        # Carry-over: existing trade blocks new entries
        if cfg.carry_over_blocks_new_entry and self._active_trade:
            logger.info("Carry-over trade active — skipping trigger")
            return

        # Already watching this direction
        if watcher.is_active:
            logger.info("%s watcher already armed — skipping duplicate", trigger.direction.value)
            return

        # AI filter
        ai_result = {"approved": True, "decision": "DISABLED", "confidence": 0, "reason": ""}
        if cfg.ai_filter_enabled:
            ai_result = run_ai_filter(
                self._candles.completed_candles, trigger, self._daily.orb, cfg
            )
            trigger.ai_result = ai_result  # stash for trade creation

        self._notifier.trigger_detected(
            trigger.direction.value,
            trigger.reference_level,
            trigger.sl_price,
            ai_result.get("decision"),
        )

        if not ai_result["approved"]:
            self._notifier.trigger_rejected(trigger.direction.value, ai_result.get("reason", ""))
            logger.info("AI rejected %s trigger — skipping", trigger.direction.value)
            return

        watcher.arm(trigger, trigger_candle.timestamp)
        logger.info(
            "Armed %s watcher: ref=%.2f sl=%.2f",
            trigger.direction.value, trigger.reference_level, trigger.sl_price
        )

    # -----------------------------------------------------------------------
    # Trade entry
    # -----------------------------------------------------------------------

    def _execute_entry(self, trigger: TriggerSetup, entry_price: float):
        cfg = self._cfg

        qty = calculate_position(entry_price, trigger.sl_price, cfg)
        if qty == 0:
            logger.error("Position size 0 — skipping trade")
            return

        # Place order
        success = place_entry(cfg, trigger.direction, qty)
        if not success:
            logger.error("Entry order failed — not recording trade")
            return

        trade = create_trade(trigger, entry_price, qty)

        # Attach AI result if available
        ai = getattr(trigger, "ai_result", {})
        trade.ai_decision   = ai.get("decision")
        trade.ai_confidence = ai.get("confidence")
        trade.ai_reason     = ai.get("reason")

        # Setup trail manager
        self._sl_mgr.setup(trade, cfg.initial_rr, cfg.trail_step)

        # Update state
        self._active_trade = trade
        self._daily.active_trade = trade
        if trigger.direction == Direction.LONG:
            self._daily.long_entries += 1
        else:
            self._daily.short_entries += 1

        self._notifier.trade_entry(trade)
        self._trade_log.log(trade)
        self._save()

        logger.info(
            "ENTERED %s @ %.2f  sl=%.2f  qty=%.4f  R=%.2f",
            trade.direction.value, entry_price, trade.sl_price, qty, trade.r_size
        )

    # -----------------------------------------------------------------------
    # Trade management
    # -----------------------------------------------------------------------

    def _on_trail(self):
        trade = self._active_trade
        if not trade:
            return
        self._notifier.trail_update(trade)
        self._save()
        logger.info(
            "Trail step %d: sl=%.2f target=%.2f",
            trade.trail_steps_hit, trade.sl_price, trade.current_target
        )

    def _on_exit(self, exit_price: float):
        trade = self._active_trade
        if not trade:
            return

        trade.exit_price = exit_price
        trade.exit_time  = now_ist()
        trade.state      = TradeState.CLOSED
        trade.exit_reason = (
            ExitReason.TRAIL_STOP if trade.trail_steps_hit > 0 else ExitReason.STOP_LOSS
        )

        pnl = trade.pnl or 0.0
        self._daily.realized_pnl += pnl

        # Place exit order
        place_exit(self._cfg, trade.direction, trade.quantity)

        # Reset
        self._sl_mgr.reset()
        self._active_trade = None
        self._daily.active_trade = None

        self._notifier.trade_exit(trade)
        self._trade_log.log(trade)

        # Daily loss limit
        if (
            self._cfg.stop_trading_after_limit
            and self._daily.realized_pnl <= -self._cfg.daily_loss_limit
        ):
            self._daily.trading_halted = True
            self._notifier.daily_loss_limit_hit(self._daily.realized_pnl, self._cfg.daily_loss_limit)
            logger.warning("Daily loss limit hit — trading halted")

        self._save()
        logger.info(
            "EXITED %s @ %.2f  pnl=₹%.2f (%.2fR)  reason=%s",
            trade.direction.value, exit_price, pnl,
            trade.pnl_r or 0, trade.exit_reason.value
        )

    # -----------------------------------------------------------------------
    # Run loop
    # -----------------------------------------------------------------------

    def run(self):
        cfg = self._cfg
        logger.info("=== BTC ORB Bot starting ===")
        self._notifier.bot_started()
        self._running = True

        tick_q = TickQueue(cfg.cryptx_ws_url, cfg.instrument, cfg.cryptx_api_key)
        tick_q.start()

        def _shutdown(sig, frame):
            logger.info("Shutdown signal received")
            self._running = False
            tick_q.stop()
            self._notifier.bot_stopped("signal")

        signal.signal(signal.SIGINT,  _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        logger.info("Waiting for ticks from %s ...", cfg.cryptx_ws_url)

        while self._running:
            tick = tick_q.get(timeout=1.0)
            if tick is None:
                continue
            price, ts = tick
            try:
                self.process_tick(price, ts)
            except Exception as exc:
                logger.exception("Unhandled error in process_tick: %s", exc)

        logger.info("=== Bot stopped ===")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg, _ = bootstrap()

    # Validate essential env vars are real (not placeholder)
    if not cfg.cryptx_api_key or cfg.cryptx_api_key.startswith("YOUR"):
        logger.error("Set CRYPTX_API_KEY in .env first")
        sys.exit(1)

    bot = ORBBot(cfg)
    bot.run()
