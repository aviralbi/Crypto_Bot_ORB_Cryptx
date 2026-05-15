╔══════════════════════════════════════════════════════════════════════════════╗
║           BTC OPENING RANGE BREAKOUT (ORB) TRADING BOT — FULL GUIDE         ║
║                  Built for CryptX India Futures Exchange                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

This guide explains everything about this project from scratch.
No trading or programming experience needed to understand the concepts.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — WHAT IS THIS BOT?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is an automated trading bot for Bitcoin (BTC) futures on the CryptX India
exchange. It runs a strategy called "Opening Range Breakout" (ORB).

"Automated" means the bot:
  - Watches BTC price live, 24/7
  - Detects trading setups by itself
  - Places real buy/sell orders without you clicking anything
  - Manages stop losses and profit targets automatically

You only need to:
  - Start the bot once with "python main.py"
  - Let it run
  - Check Telegram notifications (optional) or CSV trade logs


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2 — THE STRATEGY EXPLAINED (What does the bot actually do?)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — BUILD THE OPENING RANGE (5:30 AM to 9:30 AM IST)
──────────────────────────────────────────────────────────
During the first 4 hours of the Indian morning session, the bot watches every
15-minute candle (a candlestick chart bar that represents 15 minutes of price).

  - It records the HIGHEST price reached in any candle during this window → OR High
  - It records the LOWEST price reached in any candle during this window → OR Low

This price band (OR High to OR Low) is called the "Opening Range" (OR).
Think of it as the "morning battle zone" where bulls and bears fight.

Example:
  5:30 AM candle: H=83000, L=82500
  5:45 AM candle: H=83200, L=82400
  ...continuing until...
  9:15 AM candle (the last 15m candle before 9:30): H=83100, L=82600

  OR High = 83200  (highest of all highs)
  OR Low  = 82400  (lowest of all lows)


STEP 2 — DETECT A TRIGGER CANDLE (After 9:30 AM)
──────────────────────────────────────────────────
Once the OR is locked, the bot watches post-9:30 AM 15-minute candles for a
BREAKOUT — a candle that closes OUTSIDE the opening range.

LONG trigger (expecting price to go UP):
  - A 15m candle closes ABOVE OR High
  - At least 60% of the candle's body (open-to-close part) is above OR High
  - This means it's a strong breakout, not just a wick

SHORT trigger (expecting price to go DOWN):
  - A 15m candle closes BELOW OR Low
  - At least 60% of the candle's body is below OR Low

Why 60%? A candle with 60%+ body above/below the level is a strong, committed
move. A candle that barely closes above with a tiny body is a weak signal.

The 60% threshold is configurable (body_threshold_pct in config.py).


STEP 3 — ENTRY (Tick Break of Trigger Candle High/Low)
────────────────────────────────────────────────────────
The bot does NOT enter the moment a trigger candle closes. Instead:

For a LONG trade:
  - The trigger candle's HIGH becomes the "entry level"
  - The bot watches the NEXT candle
  - The instant BTC price ticks ABOVE that high → BUY order placed (entry)

For a SHORT trade:
  - The trigger candle's LOW becomes the "entry level"
  - The bot watches the NEXT candle
  - The instant BTC price ticks BELOW that low → SELL order placed (entry)

If the next candle closes WITHOUT price breaking the entry level, the trigger
is cancelled (invalidated) — the bot waits for the next trigger.

Gap Entry: If the next candle OPENS already beyond the entry level (a "gap"),
the bot enters immediately at the open price (configurable).


STEP 4 — STOP LOSS
────────────────────
The Stop Loss (SL) is placed at the LOW of the candle BEFORE the trigger candle
(for longs) or the HIGH of the candle before the trigger (for shorts).

Why the candle before? That candle represents the last "normal" price action
before the breakout. If price falls back to that level, the breakout has failed.

Example:
  Pre-trigger candle: Low = 83050
  Trigger candle: Closed above OR High at 83500
  Entry: 83520 (tick break of trigger high)
  Stop Loss: 83050 (low of candle before trigger)
  Risk (1R) = 83520 - 83050 = 470 points


STEP 5 — TARGETS AND TRAILING STOP LOSS
─────────────────────────────────────────
The bot uses an R-multiple system (R = your risk per trade).

  Initial target: 1:2 risk/reward (you risk 1R to make 2R)

  When price reaches the 1:2 target:
    → Stop loss MOVES UP to the 1:2 level (locked in profit)
    → New target becomes 1:3

  When price reaches the 1:3 target:
    → Stop loss MOVES UP to the 1:3 level
    → New target becomes 1:4

  ...and so on until either price hits stop loss or bot decides to stop trailing

This is called "step trailing" — profits are locked in as the trade goes further.
If price reverses, you exit at the last locked level (never losing from there).


STEP 6 — POSITION SIZING (How much BTC to buy?)
─────────────────────────────────────────────────
The bot calculates position size automatically based on:

  Risk Amount  = Capital × Risk%
               = 100,000 INR × 5% = 5,000 INR

  Quantity     = Risk Amount / Stop Loss Distance
               = 5,000 / 470 = 10.63... → floored to 10.638 BTC (using leverage)

Wait, BTC costs crores — how do we afford it?
  → Leverage! CryptX offers up to 100x leverage.
  → With 25x leverage and 1,00,000 INR capital, you can control 25,00,000 INR of BTC.
  → But your actual RISK (loss if SL hits) is still limited to Risk% of your capital.


STEP 7 — DAILY LIMITS AND SAFETY
──────────────────────────────────
The bot has several safety guardrails:
  - Max 1 long trade per day (configurable)
  - Max 1 short trade per day (configurable)
  - Daily loss limit: if total loss reaches ₹10,000, trading halts for the day
  - Daily profit target: optionally stop trading once target is hit


STEP 8 — AI FILTER (Optional Quality Check)
─────────────────────────────────────────────
Before entering a trade, the bot can optionally consult Google's Gemini AI:
  1. It generates a candlestick chart showing the OR and trigger
  2. Sends the chart image to Gemini with context about the trade setup
  3. Gemini looks at the chart like a human trader would
  4. Gemini replies APPROVE or REJECT with a confidence score and reason

Modes:
  "shadow"  = AI runs, you see its opinion in logs, but it never blocks trades
  "active"  = AI can actually reject trades it doesn't like

This adds a visual sanity check powered by AI vision.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 3 — PROJECT FILE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  btc-orb-bot/
  ├── main.py          ← Start here. Runs the bot. Wires all modules together.
  ├── config.py        ← ALL settings. Edit this to customize the bot.
  ├── strategy.py      ← The brain. ORB math, trigger logic, trailing SL.
  ├── models.py        ← Data structures: Candle, Trade, OpeningRange, etc.
  ├── data_feed.py     ← Connects to CryptX live price feed (Socket.IO).
  ├── execution.py     ← Places orders on CryptX via REST API. Telegram alerts.
  ├── ai_filter.py     ← Generates chart images. Calls Gemini AI for analysis.
  ├── utils.py         ← Helpers: timezone conversion, logging, config loader.
  ├── requirements.txt ← Python packages needed. Install with pip.
  ├── .env.example     ← Template for your API keys. Copy → rename to .env
  ├── tests/
  │   └── test_strategy.py  ← Unit tests for strategy math
  └── PROJECT_GUIDE.txt     ← This file!

  Folders created automatically at runtime:
  ├── logs/
  │   ├── system.log         ← All bot events
  │   ├── trades/            ← CSV file per day with every trade
  │   ├── charts/            ← Chart PNG images sent to AI
  │   └── ai_decisions/      ← JSON files with AI responses
  └── state/
      └── state.json         ← Bot saves current state here (crash recovery)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 4 — HOW EACH FILE WORKS (Code Explanation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

── models.py ──────────────────────────────────────────────────────────────────
Contains the data classes (blueprints for data):

  Candle         : One 15-minute price bar (open, high, low, close, volume)
  CandleBuilder  : Takes raw price ticks → builds Candle objects
  OpeningRange   : Stores OR High, OR Low, and when it was formed
  TriggerSetup   : Information about a detected breakout trigger
  Trade          : All info about one trade (entry, SL, target, exit, P&L)
  DailyState     : Today's counter (how many trades, total P&L, halted or not)

No trading logic here — just data containers.

── strategy.py ────────────────────────────────────────────────────────────────
The heart of the bot. Six classes/functions:

  ORBCalculator    : Watches 15m candles 5:30–9:30 AM → builds the OR
  TriggerDetector  : Checks each candle after 9:30 for breakout conditions
  EntryWatcher     : Armed with a trigger, waits for tick-level price break
  SLTrailManager   : Monitors active trade, steps up SL as targets are hit
  calculate_position: Computes how many BTC to buy based on risk settings
  create_trade     : Factory that builds a Trade object at entry time

All pure math — no network calls, no side effects.

── data_feed.py ────────────────────────────────────────────────────────────────
Connects to CryptX's real-time price feed.

  CryptX uses Socket.IO (not plain WebSocket).
  URL: https://fawss.cryptxindia.com

  CryptXFeed   : Opens Socket.IO connection, subscribes to "btcusdt@aggTrade",
                 calls on_tick(price, timestamp) for every trade that happens.
  TickQueue    : Thread-safe wrapper — feed runs in background thread,
                 main loop reads ticks via queue.get()

aggTrade event fields used:
  "p" = price of that trade
  "E" = timestamp in milliseconds (Unix epoch)

── execution.py ───────────────────────────────────────────────────────────────
Places real orders on CryptX via REST API.

  _sign()         : Creates HMAC-SHA256 signature (security requirement of API)
  _signed_post()  : Sends signed POST request to CryptX with retry logic
  place_entry()   : Places BUY (long) or SELL (short) market order
  place_exit()    : Places closing order (reduceOnly=True)

  Paper trading mode: if paper_trading=True in config, SKIPS real API calls
  and just logs "[PAPER] ENTRY/EXIT" — safe for testing.

  TelegramNotifier : Sends formatted messages to your Telegram bot
  TradeLogger      : Writes completed trades to CSV files in logs/trades/

── ai_filter.py ────────────────────────────────────────────────────────────────
Optional AI analysis before each trade.

  generate_chart()      : Uses mplfinance to draw a candlestick chart with:
                          - OR High line (green dashed)
                          - OR Low line (red dashed)
                          - Trigger candle marked with orange vertical line
                          Saves to logs/charts/ as PNG

  _call_gemini_vision() : Sends chart image + trade context to Google Gemini
                          Parses JSON response: {"decision": "APPROVE", ...}

  run_ai_filter()       : Full pipeline. Returns dict with approved=True/False

── utils.py ───────────────────────────────────────────────────────────────────
Shared helpers used across all files:

  now_ist()     : Current time in India timezone
  to_ist()      : Convert any datetime to IST
  make_ist_time : Build a datetime from "HH:MM" string
  Config        : Wraps the CONFIG dict, makes keys accessible as obj.key
  load_config   : Loads config.py and returns Config object
  setup_logging : Sets up colored terminal + file logging
  get_logger    : Returns a named logger (e.g. "orb.strategy")
  round_qty     : Floors BTC quantity to allowed decimal places

── main.py ────────────────────────────────────────────────────────────────────
Entry point. The ORBBot class wires everything together:

  __init__      : Creates all components (ORBCalculator, TriggerDetector, etc.)
                  Restores state from state.json if bot was restarted

  run()         : Starts tick feed, enters main loop
                  For each tick → calls process_tick()

  process_tick  : 1. Feed tick to CandleBuilder
                  2. On candle close → check OR, check triggers
                  3. If watcher armed → check for entry break
                  4. If in trade → check SL/trail

  _execute_entry: Calculate position → place order → create Trade → save state
  _on_trail     : Step up SL → notify Telegram → save state
  _on_exit      : Place exit order → calculate P&L → log trade → save state


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 5 — HOW TO SET UP (Step by Step from Zero)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: Install Python
  - Download Python 3.11 or higher from python.org
  - On Mac: prefer Anaconda (anaconda.com) — avoids system Python conflicts
  - Verify: open Terminal and type:  python --version
  - Should show: Python 3.11.x or 3.12.x

STEP 2: Install Required Packages
  Open Terminal, go to the project folder:

    cd /path/to/btc-orb-bot

  Install all packages at once:

    pip install pandas numpy mplfinance matplotlib google-genai python-dotenv "python-socketio[client]" requests pytz "python-telegram-bot>=20.0"

  Or use the requirements file:

    pip install -r requirements.txt

STEP 3: Get API Keys

  A) CryptX API Key and Secret:
     - Log in to your CryptX account
     - Go to Settings → API Keys
     - Create a new API key
     - Copy the API Key and API Secret

  B) Gemini API Key (free):
     - Go to https://aistudio.google.com
     - Click "Get API Key" → Create API Key in new project
     - Copy the key (starts with "AIza...")
     - Free tier gives ~1500 requests/day — more than enough

  C) Telegram Bot (optional — for trade notifications):
     - Open Telegram → search for @BotFather
     - Send /newbot → follow instructions → copy the token
     - Find your chat ID by messaging @userinfobot

STEP 4: Create Your .env File
  - Copy .env.example → rename to .env
  - Fill in your real API keys:

    CRYPTX_API_KEY=your_actual_key
    CRYPTX_API_SECRET=your_actual_secret
    GEMINI_API_KEY=AIzaSyC...your_gemini_key

  IMPORTANT: Never share this .env file. Never commit it to GitHub.
  The .gitignore file already prevents it from being accidentally uploaded.

STEP 5: Review config.py
  Open config.py and check these important settings:

    "paper_trading": True       ← Start with True! Test safely first.
    "capital": 100000           ← Your actual trading capital in INR
    "risk_per_trade_pct": 5.0   ← % risked per trade (5% = safe for learning)
    "leverage": 25              ← Match your CryptX account leverage setting
    "telegram_enabled": False   ← Set True if you want alerts

STEP 6: Run the Bot
  In Terminal:

    python main.py

  You'll see colored logs like:
    09:30:00  INFO  main       === BTC ORB Bot starting ===
    09:30:01  INFO  data       Feed starting: https://fawss.cryptxindia.com
    09:30:02  INFO  data       Socket.IO connected — subscribing btcusdt@aggTrade
    09:30:03  INFO  strat      OR accumulation started 2025-05-06

  Press Ctrl+C to stop the bot at any time.

STEP 7: Read the Output (What do the logs mean?)
  Log line format:  TIME  LEVEL  MODULE  MESSAGE

  TIME   : When this happened (HH:MM:SS)
  LEVEL  : INFO (normal), WARNING (non-critical issue), ERROR (something failed)
  MODULE : Which file logged it (main, strat, data, exec, ai)

  Key messages to watch for:
    "OR formed: H=83200 L=82400"    → Opening Range locked in for the day
    "LONG trigger: ref=83250 sl=..."→ Potential LONG setup detected
    "ENTERED LONG @ 83270"          → Bot bought BTC
    "Trail step 1: sl=..."          → Bot moved stop loss up (locking profit)
    "EXITED LONG @ 83800 pnl=..."   → Trade closed, shows profit/loss
    "Daily loss limit hit"          → Bot stopped for the day (safety)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 6 — WHAT CAN YOU CHANGE? (Customization Guide)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All customization happens in config.py. Here's what each group of settings
does and what you can safely change:

── Opening Range Window ───────────────────────────────────────────────────────
  "or_start_time": "05:30"     → When OR starts building (IST)
  "or_end_time":   "09:30"     → When OR locks in (IST)

  Change to: "09:15" / "10:00" to experiment with different session windows.
  For example, "09:15"–"11:00" captures the Indian market open (if CryptX
  tracks NSE sentiment).

── How Strict the Trigger Must Be ────────────────────────────────────────────
  "body_threshold_pct": 60

  This is the percentage of the candle's body that must be OUTSIDE the OR.
  - 50 = loose, more signals, less quality
  - 60 = default, balanced
  - 70 = strict, fewer signals, higher quality

  Lower = more trades. Higher = fewer but stronger trades.

── Risk Per Trade ─────────────────────────────────────────────────────────────
  "risk_per_trade_pct": 5.0    → Risk 5% of capital per trade

  IMPORTANT: This is the most impactful setting.
  - 1%–2% = very conservative (professional standard)
  - 5%     = moderate (what this bot defaults to)
  - 10%+   = aggressive (can lose capital quickly on losing streaks)

  Start with 1–2% when testing live, increase only after 20+ trades of data.

── Profit Target and Trailing ────────────────────────────────────────────────
  "initial_rr":    2.0         → First target at 1:2 risk/reward
  "trail_step":    1.0         → Each trail step is 1R further
  "trail_enabled": True        → Use trailing SL (False = exit at first target)

  Examples:
    initial_rr=2.0, trail_step=1.0 → Targets at 2R, 3R, 4R, 5R...
    initial_rr=1.5, trail_step=0.5 → Targets at 1.5R, 2R, 2.5R, 3R...
    trail_enabled=False             → Just take profit at initial_rr, no trailing

── Daily Trade Limits ────────────────────────────────────────────────────────
  "max_long_entries_per_day":  1   → One long trade per day max
  "max_short_entries_per_day": 1   → One short trade per day max
  "allow_both_directions_same_day": True → Can go long AND short same day

  For beginners: keep both at 1. One trade per day per direction is plenty.

── Safety Limits ─────────────────────────────────────────────────────────────
  "daily_loss_limit":    10000    → Stop trading if you lose ₹10,000 today
  "daily_profit_target": None     → No automatic profit stop (set e.g. 15000)

  These protect you from bad days. ALWAYS set daily_loss_limit.

── AI Filter ─────────────────────────────────────────────────────────────────
  "ai_filter_enabled": True       → Turn on/off (False = no AI check)
  "ai_filter_mode":    "shadow"   → "shadow" = observe only, "active" = enforces
  "ai_min_confidence": 6          → In active mode, reject if confidence < 6

  Start with "shadow" mode. Collect 20–30 trades of AI decisions.
  Check logs/ai_decisions/ to see if AI was right or wrong.
  Only switch to "active" if AI accuracy is > 60%.

── Paper Trading ─────────────────────────────────────────────────────────────
  "paper_trading": True           → NO real orders. Simulated trading only.

  ALWAYS start with paper_trading=True. Run for at least 2 weeks.
  Only set to False when you are confident in the strategy and the code.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 7 — COMMON QUESTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q: Do I need to leave my computer on?
A: Yes. The bot needs to run continuously. Options:
   - Leave laptop running 24/7
   - Use a cloud server (AWS EC2 / DigitalOcean / Google Cloud) — recommended
   - A ₹500/month basic cloud server is enough

Q: What if my internet goes down?
A: The bot auto-reconnects to CryptX feed. If you have an open trade, it
   restores its state from state.json when restarted. The bot saves state
   after every important event (entry, trail, exit).

Q: The bot ran but no trades happened today. Why?
A: Several possibilities:
   - OR formed but no candle broke outside with 60%+ body → no trigger
   - Trigger fired but entry candle didn't break the reference level
   - You already hit max_long_entries_per_day or max_short_entries_per_day
   - trading_halted = True from daily loss limit
   Check the log file (logs/system.log) for the full story.

Q: Can the bot lose all my money?
A: If you set risk_per_trade_pct=5% and daily_loss_limit=10000, the worst day
   possible (if SL hits AND bot malfunctions) is limited to that daily limit.
   Never use risk > 5% without deep understanding of the strategy.
   Start with paper trading and build confidence first.

Q: I see "API attempt 1/3: HTTP 401" in logs. What's wrong?
A: Your CRYPTX_API_KEY or CRYPTX_API_SECRET in .env is wrong. Double-check them.

Q: I see "AI filter error" in logs. Is that a problem?
A: No. ai_fallback_action="approve" means if AI fails, the bot still takes
   the trade. Gemini API may occasionally be slow or unavailable — that's fine.

Q: What's the difference between entry_price and reference_level?
A: reference_level = the trigger candle's high (for long) or low (for short)
   entry_price = the actual price the next tick crossed that level
   Usually very close, but can differ slightly due to market volatility.

Q: Can I run multiple bots for different coins?
A: Yes, but you'd need a separate folder with separate config and .env for each.
   The code only supports one instrument per bot instance.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 8 — HOW TO READ TRADE CSV LOGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every completed trade is saved to: logs/trades/trades_YYYY-MM-DD.csv

Columns:
  timestamp      : When the trade was logged
  id             : Unique 8-character trade ID
  direction      : LONG or SHORT
  entry_price    : Price we entered at
  initial_sl     : Original stop loss price
  sl_price       : Final stop loss price (may have moved due to trailing)
  target_price   : Last active target price
  qty            : BTC quantity traded
  exit_price     : Price we exited at
  exit_reason    : STOP_LOSS | TRAIL_STOP | DAILY_LOSS_LIMIT | MANUAL
  pnl_inr        : Profit/loss in INR (negative = loss)
  pnl_r          : Profit/loss in R-multiples (+2.0 = hit 2R target)
  trail_steps_hit: How many trail steps before exit (0 = direct SL hit)
  ai_decision    : APPROVE or REJECT (what AI said)
  ai_confidence  : AI confidence score 1-10
  ai_reason      : AI's explanation

Open this in Excel or Google Sheets to analyze your performance.
Key metric to track: Average pnl_r per trade. Target: > +0.5R on average.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 9 — ADVANCED: UNDERSTANDING THE CODE FLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For students who want to understand the code deeply:

TICK FLOW (every price update from CryptX):

  CryptX server
       ↓ Socket.IO aggTrade event (price + timestamp)
  CryptXFeed._on_trade()
       ↓ (price, ts) → queue
  TickQueue.get()
       ↓
  ORBBot.process_tick(price, ts)
       ↓
  CandleBuilder.on_tick(price, ts)
       ├── if candle still open: update high/low/close
       └── if new bar: close current → return closed Candle
              ↓
         ORBBot._on_candle_close(candle)
              ├── ORBCalculator.on_candle(candle)
              │     └── if last OR candle: return OpeningRange
              └── TriggerDetector.check(candle, prev, orb)
                    └── if breakout: return TriggerSetup
                           ↓
                      ORBBot._process_trigger(trigger)
                           ├── check limits, halted, carry-over
                           ├── run AI filter (optional)
                           └── EntryWatcher.arm(trigger)
       ↓
  back to tick loop...
  EntryWatcher.on_tick(price)
       └── if price breaks reference level → entry_price
              ↓
         ORBBot._execute_entry(trigger, entry_price)
              ├── calculate_position(entry, sl, cfg)
              ├── place_entry(cfg, direction, qty)  ← real API call
              ├── create_trade(trigger, entry_price, qty)
              └── SLTrailManager.setup(trade, initial_rr, trail_step)
       ↓
  SLTrailManager.on_tick(price)
       ├── if price hits SL → "exit" → ORBBot._on_exit(price)
       └── if price hits target → "trail" → ORBBot._on_trail()
              └── step up SL, set new target


THREADING MODEL:
  Main thread : Runs the main loop, calls process_tick()
  sio-feed    : Background daemon thread, receives Socket.IO events

  They communicate via TickQueue (thread-safe queue.Queue)
  This prevents the Socket.IO thread from blocking trade logic.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 10 — KNOWN LIMITATIONS AND THINGS TO BE AWARE OF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. MARKET ORDERS ONLY
   The bot places MARKET orders (fills at current price, guaranteed).
   This means slippage is possible during high volatility.
   Limit orders are NOT supported yet.

2. ONE POSITION AT A TIME
   The bot tracks one active trade. It cannot manage two simultaneous trades.

3. ONLY 15-MINUTE CANDLES
   execution_timeframe is fixed to "15m". Other timeframes are not supported.

4. CryptX ONLY
   This bot is built specifically for CryptX India's API format (HMAC-SHA256,
   Socket.IO feed). It will NOT work on Binance, WazirX, or other exchanges
   without significant code changes.

5. NO HISTORICAL BACKTESTING IN THIS VERSION
   The bot runs live only. Backtest code was removed. To backtest the strategy,
   you would need historical OHLCV data and a separate backtest script.

6. GEMINI API FREE TIER LIMITS
   Free tier: ~1500 requests/day. With AI filter active, each trigger uses 1
   request. In normal trading (1–3 triggers/day) this is never a problem.

7. CARRY-OVER TRADES
   If you have an open trade at midnight, the bot carries it to the next day.
   The daily counter resets but the trade stays active.
   carry_over_blocks_new_entry=True means no new entry while carry-over is open.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 11 — QUICK REFERENCE CHEAT SHEET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Start bot:            python main.py
  Stop bot:             Ctrl + C
  View logs (live):     tail -f logs/system.log
  View trade history:   open logs/trades/ folder in Excel/Sheets

  Test safely:          set paper_trading=True in config.py
  Go live:              set paper_trading=False in config.py

  Change risk:          change risk_per_trade_pct in config.py
  Change daily limit:   change daily_loss_limit in config.py
  Disable AI:           set ai_filter_enabled=False in config.py
  Enable Telegram:      set telegram_enabled=True, fill .env tokens

  If bot crashes:       just restart with python main.py
                        it restores state from state/state.json

  Missing packages:     pip install -r requirements.txt
  Wrong Python version: use "python" not "python3" if on Anaconda

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
END OF GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
