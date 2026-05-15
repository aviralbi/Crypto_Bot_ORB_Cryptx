"""
CryptX REST API order execution, Telegram notifications, CSV trade logger.
"""

import csv
import hashlib
import hmac
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from models import Trade, Direction, ExitReason, OpeningRange
from utils import get_logger, now_ist

logger = get_logger("execution")

_BASE_URL = "https://fapi.cryptxindia.com"


# ---------------------------------------------------------------------------
# Signature + signed POST helper
# ---------------------------------------------------------------------------

def _sign(secret: str, data: str) -> str:
    return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_post(
    endpoint: str,
    params: dict,
    api_key: str,
    api_secret: str,
    retries: int = 3,
    delay: float = 2.0,
) -> tuple[bool, dict]:
    params["timestamp"] = str(int(time.time() * 1000))
    body_str = json.dumps(params, separators=(",", ":"))
    sig = _sign(api_secret, body_str)
    headers = {
        "api-key": api_key,
        "signature": sig,
        "Content-Type": "application/json",
    }
    url = f"{_BASE_URL}{endpoint}"

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                logger.info("API OK [%s]", endpoint)
                return True, resp.json()
            logger.warning(
                "API attempt %d/%d: HTTP %d — %s",
                attempt, retries, resp.status_code, resp.text[:200],
            )
        except Exception as exc:
            logger.warning("API attempt %d/%d error: %s", attempt, retries, exc)
        if attempt < retries:
            time.sleep(delay)

    logger.error("API FAILED after %d attempts: %s %s", retries, endpoint, params)
    return False, {}


# ---------------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------------

def place_entry(cfg, direction: Direction, qty: float) -> bool:
    side = "BUY" if direction == Direction.LONG else "SELL"
    if getattr(cfg, "paper_trading", False):
        logger.info("[PAPER] ENTRY %s %s qty=%.4f — no real order", side, cfg.instrument, qty)
        return True
    params = {
        "placeType":    "ORDER_FORM",
        "quantity":     qty,
        "side":         side,
        "symbol":       cfg.instrument,
        "type":         "MARKET",
        "reduceOnly":   False,
        "marginAsset":  "INR",
        "deviceType":   "WEB",
        "userCategory": "EXTERNAL",
    }
    logger.info("Placing ENTRY: %s %s qty=%.4f", side, cfg.instrument, qty)
    ok, resp = _signed_post(
        "/v1/order/place-order", params,
        cfg.cryptx_api_key, cfg.cryptx_api_secret,
    )
    if ok:
        logger.info("Entry confirmed: orderId=%s", resp.get("clientOrderId", "?"))
    return ok


def place_exit(cfg, direction: Direction, qty: float) -> bool:
    side = "SELL" if direction == Direction.LONG else "BUY"
    if getattr(cfg, "paper_trading", False):
        logger.info("[PAPER] EXIT %s %s qty=%.4f — no real order", side, cfg.instrument, qty)
        return True
    params = {
        "placeType":    "ORDER_FORM",
        "quantity":     qty,
        "side":         side,
        "symbol":       cfg.instrument,
        "type":         "MARKET",
        "reduceOnly":   True,
        "marginAsset":  "INR",
        "deviceType":   "WEB",
        "userCategory": "EXTERNAL",
    }
    logger.info("Placing EXIT: %s %s qty=%.4f", side, cfg.instrument, qty)
    ok, resp = _signed_post(
        "/v1/order/place-order", params,
        cfg.cryptx_api_key, cfg.cryptx_api_secret,
    )
    if ok:
        logger.info("Exit confirmed: orderId=%s", resp.get("clientOrderId", "?"))
    return ok


# ---------------------------------------------------------------------------
# Telegram notifier
# ---------------------------------------------------------------------------

class TelegramNotifier:
    def __init__(self, cfg):
        self._enabled = cfg.telegram_enabled
        self._token = cfg.get("telegram_bot_token", "")
        self._chat  = cfg.get("telegram_chat_id", "")

    def _send(self, text: str):
        if not self._enabled or not self._token or not self._chat:
            return
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Telegram failed: %d %s", resp.status_code, resp.text[:100])
        except Exception as exc:
            logger.warning("Telegram error: %s", exc)

    def or_formed(self, orb: OpeningRange):
        self._send(
            f"📊 <b>OR Formed — {orb.date.strftime('%d %b %Y')}</b>\n"
            f"High : <code>{orb.high:.2f}</code>\n"
            f"Low  : <code>{orb.low:.2f}</code>\n"
            f"Range: <code>{orb.range_size:.2f}</code> pts"
        )

    def trigger_detected(self, direction: str, ref: float, sl: float, ai_decision: Optional[str] = None):
        arrow = "🔺" if direction == "LONG" else "🔻"
        ai_line = f"\nAI : <code>{ai_decision}</code>" if ai_decision else ""
        self._send(
            f"{arrow} <b>Trigger — {direction}</b>\n"
            f"Ref: <code>{ref:.2f}</code>   SL: <code>{sl:.2f}</code>{ai_line}"
        )

    def trigger_rejected(self, direction: str, reason: str):
        self._send(
            f"🚫 <b>AI Rejected — {direction}</b>\n"
            f"Reason: {reason}"
        )

    def trade_entry(self, trade: Trade):
        arrow = "🟢" if trade.direction == Direction.LONG else "🔴"
        self._send(
            f"{arrow} <b>ENTRY — {trade.direction.value}</b>  #{trade.id}\n"
            f"Entry : <code>{trade.entry_price:.2f}</code>\n"
            f"SL    : <code>{trade.sl_price:.2f}</code>\n"
            f"Target: <code>{trade.current_target:.2f}</code>  (1:2)\n"
            f"Qty   : <code>{trade.quantity:.4f} BTC</code>\n"
            f"R     : <code>{trade.r_size:.2f}</code> pts"
        )

    def trail_update(self, trade: Trade):
        self._send(
            f"📈 <b>Trail Step {trade.trail_steps_hit} — {trade.direction.value}</b>\n"
            f"New SL    : <code>{trade.sl_price:.2f}</code>\n"
            f"Next target: <code>{trade.current_target:.2f}</code>  (1:{trade.trail_steps_hit + 2})"
        )

    def trade_exit(self, trade: Trade):
        pnl   = trade.pnl   or 0.0
        pnl_r = trade.pnl_r or 0.0
        emoji = "💰" if pnl >= 0 else "💸"
        reason = trade.exit_reason.value if trade.exit_reason else "?"
        self._send(
            f"{emoji} <b>EXIT — {trade.direction.value}</b>  #{trade.id}\n"
            f"Entry : <code>{trade.entry_price:.2f}</code>   Exit: <code>{trade.exit_price:.2f}</code>\n"
            f"P&amp;L  : <code>₹{pnl:+.2f}</code>  ({pnl_r:+.2f}R)\n"
            f"Reason: {reason}   Trails: {trade.trail_steps_hit}"
        )

    def daily_loss_limit_hit(self, realized_pnl: float, limit: float):
        self._send(
            f"⛔ <b>DAILY LOSS LIMIT HIT</b>\n"
            f"Loss : <code>₹{abs(realized_pnl):.2f}</code>\n"
            f"Limit: <code>₹{limit:.2f}</code>\n"
            f"Trading halted for rest of day."
        )

    def daily_summary(self, date: str, pnl: float, trades: int, halted: bool):
        status = "⛔ HALTED" if halted else "✅ Normal"
        self._send(
            f"📅 <b>Daily Summary — {date}</b>\n"
            f"P&amp;L   : <code>₹{pnl:+.2f}</code>\n"
            f"Trades: {trades}   Status: {status}"
        )

    def bot_started(self):
        self._send("🤖 <b>BTC ORB Bot started</b>")

    def bot_stopped(self, reason: str = ""):
        self._send(f"🛑 <b>Bot stopped</b>{': ' + reason if reason else ''}")


# ---------------------------------------------------------------------------
# Trade logger (CSV)
# ---------------------------------------------------------------------------

_HEADERS = [
    "timestamp", "id", "direction",
    "entry_price", "initial_sl", "sl_price", "target_price",
    "qty", "exit_price", "exit_reason",
    "pnl_inr", "pnl_r", "trail_steps_hit",
    "ai_decision", "ai_confidence", "ai_reason",
]


class TradeLogger:
    def __init__(self, log_dir: str = "./logs/trades"):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self) -> Path:
        return self._dir / f"trades_{now_ist().strftime('%Y-%m-%d')}.csv"

    def log(self, trade: Trade):
        path = self._path()
        write_header = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_HEADERS)
            if write_header:
                w.writeheader()
            w.writerow({
                "timestamp":      now_ist().isoformat(),
                "id":             trade.id,
                "direction":      trade.direction.value,
                "entry_price":    trade.entry_price,
                "initial_sl":     trade.initial_sl,
                "sl_price":       trade.sl_price,
                "target_price":   trade.current_target,
                "qty":            trade.quantity,
                "exit_price":     trade.exit_price   or "",
                "exit_reason":    trade.exit_reason.value if trade.exit_reason else "",
                "pnl_inr":        f"{trade.pnl:.2f}"   if trade.pnl   is not None else "",
                "pnl_r":          f"{trade.pnl_r:.3f}" if trade.pnl_r is not None else "",
                "trail_steps_hit": trade.trail_steps_hit,
                "ai_decision":    trade.ai_decision    or "",
                "ai_confidence":  trade.ai_confidence  or "",
                "ai_reason":      trade.ai_reason      or "",
            })
        logger.info("Trade logged → %s  pnl=%s", path.name, f"₹{trade.pnl:.2f}" if trade.pnl else "open")
