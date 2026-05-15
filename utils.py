"""
Config loader, logging, IST timezone helpers, rounding utils.
"""

import os
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, time
from typing import Any, Optional

import pytz
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent
IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.utc


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(IST)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    return dt.astimezone(UTC)


def make_ist_time(time_str: str, date: Optional[datetime] = None) -> datetime:
    """Build IST-aware datetime from 'HH:MM' string."""
    h, m = map(int, time_str.split(":"))
    base = date.date() if date else now_ist().date()
    return IST.localize(datetime.combine(base, time(h, m, 0)))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class Config:
    def __init__(self, data: dict):
        self._data = data
        for key, value in data.items():
            setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


_cfg: Optional[Config] = None


def load_config(path: Optional[Path] = None) -> Config:
    global _cfg
    load_dotenv(PROJECT_ROOT / ".env")
    from config import CONFIG
    _cfg = Config(CONFIG)
    return _cfg


def get_config() -> Config:
    if _cfg is None:
        raise RuntimeError("Call load_config() first")
    return _cfg


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_GREY   = "\033[90m"
_CYAN   = "\033[96m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_MAGENTA = "\033[95m"

_LEVEL_COLORS = {
    "DEBUG":    _GREY,
    "INFO":     _GREEN,
    "WARNING":  _YELLOW,
    "ERROR":    _RED,
    "CRITICAL": _MAGENTA,
}

# Keywords that get bold+cyan highlight in terminal (important events)
_HIGHLIGHT = ("OR formed", "ENTERED", "EXITED", "Trail step", "Trigger", "HALTED", "Bot start", "Bot stop")


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Shorten logger name: orb.main → main
        short_name = record.name.replace("orb.", "").ljust(9)
        time_str   = self.formatTime(record, "%H:%M:%S")
        level      = record.levelname[:4].ljust(4)
        color      = _LEVEL_COLORS.get(record.levelname, _RESET)
        msg        = record.getMessage()

        # Highlight important events
        is_key = any(k in msg for k in _HIGHLIGHT)
        msg_fmt = f"{_BOLD}{_CYAN}{msg}{_RESET}" if is_key else msg

        return (
            f"{_GREY}{time_str}{_RESET}  "
            f"{color}{level}{_RESET}  "
            f"{_GREY}{short_name}{_RESET}  "
            f"{msg_fmt}"
        )


class _PlainFormatter(logging.Formatter):
    """No ANSI — for file output."""
    def format(self, record: logging.LogRecord) -> str:
        short_name = record.name.replace("orb.", "").ljust(9)
        time_str   = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level      = record.levelname[:4].ljust(4)
        return f"{time_str}  {level}  {short_name}  {record.getMessage()}"


_log_ready = False


def setup_logging(log_file: Optional[str] = None, log_level: str = "INFO") -> logging.Logger:
    global _log_ready
    if _log_ready:
        return logging.getLogger("orb")

    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Terminal — colored
    ch = logging.StreamHandler()
    ch.setFormatter(_ColorFormatter())
    root.addHandler(ch)

    # File — plain
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(_PlainFormatter())
        root.addHandler(fh)

    _log_ready = True
    return logging.getLogger("orb")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"orb.{name}")


def bootstrap() -> tuple[Config, logging.Logger]:
    cfg = load_config()
    log_file = cfg.get("log_file", "./logs/system.log")
    if not Path(log_file).is_absolute():
        log_file = str(PROJECT_ROOT / log_file.lstrip("./"))
    logger = setup_logging(log_file=log_file, log_level=cfg.get("log_level", "INFO"))
    return cfg, logger


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------

def round_qty(qty: float, decimals: int) -> float:
    """Floor to lot precision (never oversize)."""
    factor = 10 ** decimals
    return int(qty * factor) / factor


def round_price(price: float, tick_size: float = 0.5) -> float:
    return round(round(price / tick_size) * tick_size, 8)
