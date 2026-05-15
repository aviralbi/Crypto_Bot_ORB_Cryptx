"""
Bot configuration. Edit values here directly.
Secret keys stay in .env — never hardcode them here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {

    # ── Opening Range ────────────────────────────────────────────────────────
    "or_start_time":  "05:30",       # IST time when OR window starts (string "HH:MM")
    "or_end_time":    "09:30",       # IST time when OR window ends   (string "HH:MM")
    "timezone":       "Asia/Kolkata", # any pytz timezone string e.g. "UTC", "US/Eastern"

    # ── Trigger Candle ───────────────────────────────────────────────────────
    "body_threshold_pct":  60,       # % of candle body above/below OR to qualify as trigger
                                     # options: 50 (loose) | 60 (default) | 70 (strict)
    "execution_timeframe": "15m",    # candle timeframe — only "15m" supported currently

    # ── Entry ────────────────────────────────────────────────────────────────
    "entry_mode":      "tick_break", # how to enter — only "tick_break" supported
    "allow_gap_entry": True,         # True = enter at open if price gaps past trigger level
                                     # False = skip trade if gap occurs

    # ── Stop Loss ────────────────────────────────────────────────────────────
    "sl_reference": "candle_before_trigger",  # only option currently
                                              # SL = low of prev candle (long) / high (short)

    # ── Targets / Trailing ───────────────────────────────────────────────────
    "initial_rr":     2.0,    # first target R multiple — options: 1.5 | 2.0 | 2.5 | 3.0
    "trail_step":     1.0,    # R step per trail level — options: 0.5 | 1.0 | 1.5
    "trail_enabled":  True,   # True = use trailing SL | False = fixed SL, exit at first target
    "max_trail_steps": None,  # None = unlimited | e.g. 3 = stop trailing after 3 steps

    # ── Daily Trade Limits ───────────────────────────────────────────────────
    "max_long_entries_per_day":    1,     # max long trades per day — options: 1 | 2 | 3
    "max_short_entries_per_day":   1,     # max short trades per day — options: 1 | 2 | 3
    "allow_both_directions_same_day": True,  # True = can take long AND short same day
                                             # False = first direction locks the day
    "retrigger_limit":             None,  # None = no limit | e.g. 2 = max 2 triggers per side
    "carry_over_blocks_new_entry": True,  # True = open trade from yesterday blocks new entries
                                          # False = allow new entry even if carry-over trade open

    # ── Capital & Risk ───────────────────────────────────────────────────────
    "capital":            100000,  # total capital in INR — e.g. 50000 | 100000 | 200000
    "risk_per_trade_pct":  5.0,   # % of capital risked per trade — options: 1 | 2 | 5 | 10
    "leverage":            25,    # exchange leverage — options: 10 | 20 | 25 | 50 | 100

    # ── Drawdown Protection ──────────────────────────────────────────────────
    "daily_loss_limit":        10000,  # INR — halt trading when loss hits this
                                       # e.g. 5000 | 10000 | 20000
    "daily_profit_target":     None,   # INR — stop trading after hitting profit target
                                       # None = no target | e.g. 15000
    "stop_trading_after_limit": True,  # True = halt rest of day after limit hit
                                       # False = keep trading (not recommended)

    # ── Position Sizing ──────────────────────────────────────────────────────
    "min_lot_size":      0.001,  # minimum BTC qty — CryptX minimum is 0.001
    "quantity_decimals": 3,      # decimal precision for qty — options: 2 | 3 | 4

    # ── Paper Trading ────────────────────────────────────────────────────────
    "paper_trading": False,  # True  = full simulation, zero real orders sent to exchange
                             # False = live trading, real orders placed
    # ── AI Provider Selection ───────────────────────────────────────────────
    "ai_provider": "openrouter",           # "gemini" or "openrouter" (primary provider)
    "use_gemini": False,                # Set False to completely disable Gemini
    "use_openrouter": True,            # Set True to enable OpenRouter fallback/primary

    # OpenRouter Settings
    "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
    "openrouter_base_url": "https://openrouter.ai/api/v1",
    "openrouter_model": "openrouter/free",          # Best free router
    # Alternative strong free vision models:
    # "google/gemma-4-26b-a4b-it:free"
    # "nvidia/nemotron-nano-2-vl:free"

    # Optional headers for OpenRouter (helps with rankings)
    "openrouter_referer": "https://your-bot-domain.com",   # Change to your domain or leave as is
    "openrouter_title": "BTC ORB Bot",
    # ── AI Vision Filter ─────────────────────────────────────────────────────
    "ai_filter_enabled":     True,      # True = run Gemini AI on each trigger
                                        # False = skip AI, take all triggers
    "ai_filter_mode":        "shadow",  # "shadow" = AI runs but never blocks trades (log only)
                                        # "active" = AI can reject trades
    "ai_model":              "gemini-2.0-flash",  # Gemini model to use
                                                   # options: "gemini-2.0-flash" (fast, free)
                                                   #          "gemini-1.5-pro"   (smarter, slower)
    "ai_min_confidence":     6,         # min confidence score (1–10) to approve in active mode
                                        # options: 5 (loose) | 6 (default) | 8 (strict)
    "chart_lookback_candles": 50,       # candles shown in chart sent to AI
                                        # options: 30 | 50 | 80
    "chart_image_path":      "./logs/charts/",       # folder to save chart PNGs
    "ai_log_path":           "./logs/ai_decisions/", # folder to save AI decision JSONs
    "ai_timeout_seconds":    10,        # seconds to wait for AI response before fallback
    "ai_fallback_action":    "approve", # what to do if AI call fails or times out
                                        # options: "approve" | "reject"

    # ── Platform ─────────────────────────────────────────────────────────────
    "exchange":       "cryptx",                         # exchange name (informational only)
    "instrument":     "BTCUSDT",                        # trading pair on CryptX
                                                        # options: "BTCUSDT" | "ETHINR" etc.
    "order_type":     "market",                         # order type — only "market" supported
    "execution_mode": "api",                            # only "api" supported
    "cryptx_ws_url":  "https://fawss.cryptxindia.com", # CryptX Socket.IO market data URL
                                                        # do not change unless CryptX changes it

    # ── State Persistence ────────────────────────────────────────────────────
    "state_file": "./state/state.json",  # where bot saves state for crash recovery
                                         # change path if needed e.g. "/tmp/state.json"

    # ── Notifications ────────────────────────────────────────────────────────
    "telegram_enabled":   False,                          # True  = send Telegram alerts
                                                          # False = silent mode
    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),  # from .env
    "telegram_chat_id":   os.getenv("TELEGRAM_CHAT_ID",   ""),  # from .env

    # ── API Keys (from .env — never hardcode here) ───────────────────────────
    "gemini_api_key":    os.getenv("GEMINI_API_KEY",    ""),  # aistudio.google.com
    "cryptx_api_key":    os.getenv("CRYPTX_API_KEY",    ""),  # CryptX dashboard → API keys
    "cryptx_api_secret": os.getenv("CRYPTX_API_SECRET", ""),  # CryptX dashboard → API keys

    # ── Logging ──────────────────────────────────────────────────────────────
    "log_level": "INFO",              # options: "DEBUG" | "INFO" | "WARNING" | "ERROR"
                                      # DEBUG = very verbose, INFO = normal, WARNING = errors only
    "log_file":  "./logs/system.log", # path to log file — None to disable file logging
}
