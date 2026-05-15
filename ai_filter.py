"""
AI Vision Filter — Supports Gemini + OpenRouter (Robust Version)
"""

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from google import genai
from google.genai import types

from models import Candle, TriggerSetup, OpeningRange, Direction
from utils import get_logger, IST, now_ist

logger = get_logger("ai_filter")


# ---------------------------------------------------------------------------
# Chart Generation (Unchanged)
# ---------------------------------------------------------------------------

def generate_chart(
    candles: list[Candle],
    orb: OpeningRange,
    trigger: TriggerSetup,
    save_path: str,
) -> str:
    """Renders mplfinance chart — unchanged from original."""
    import mplfinance as mpf
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = {
        "Open": [c.open for c in candles],
        "High": [c.high for c in candles],
        "Low": [c.low for c in candles],
        "Close": [c.close for c in candles],
        "Volume": [c.volume for c in candles],
    }
    idx = pd.DatetimeIndex([c.timestamp for c in candles])
    df = pd.DataFrame(data, index=idx)

    or_high_line = [orb.high] * len(candles)
    or_low_line = [orb.low] * len(candles)

    add_plots = [
        mpf.make_addplot(or_high_line, color="lime", linestyle="--", width=1.5),
        mpf.make_addplot(or_low_line, color="tomato", linestyle="--", width=1.5),
    ]

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    style = mpf.make_mpf_style(base_mpf_style="charles", rc={"figure.figsize": (14, 7)})

    fig, axes = mpf.plot(
        df, type="candle", addplot=add_plots, style=style,
        title=f"BTC ORB — {trigger.direction.value} Setup | OR H={orb.high:.0f} L={orb.low:.0f}",
        volume=True, returnfig=True,
    )

    trigger_idx = next((i for i, c in enumerate(candles) if c.timestamp == trigger.trigger_candle.timestamp), None)
    if trigger_idx is not None:
        ax = axes[0]
        ax.axvline(x=trigger_idx, color="orange", linewidth=2, alpha=0.8)
        label = "▲ Trigger" if trigger.direction == Direction.LONG else "▼ Trigger"
        ax.annotate(label, xy=(trigger_idx, trigger.trigger_candle.high),
                    xytext=(trigger_idx + 0.5, trigger.trigger_candle.high * 1.001),
                    fontsize=8, color="orange", arrowprops=dict(arrowstyle="->", color="orange"))

    fig.savefig(save_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", save_path)
    return save_path


# ---------------------------------------------------------------------------
# Prompt Template (Keep your original full prompt here)
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a trading filter for a BTC ORB (Opening Range Breakout) strategy.
Analyze the provided candlestick chart carefully.

Respond ONLY in this exact JSON format, no extra text:

{
  "decision": "APPROVE" or "REJECT",
  "confidence": integer between 1 and 10,
  "reason": "short clear reason"
}
"""

# ---------------------------------------------------------------------------
# Original Gemini Call (Unchanged)
# ---------------------------------------------------------------------------

def _call_gemini_vision(api_key: str, image_b64: str, trigger: TriggerSetup, orb: OpeningRange, model: str) -> dict:
    client = genai.Client(api_key=api_key)
    tc = trigger.trigger_candle
    r_size = abs(trigger.reference_level - trigger.sl_price)

    prompt = _PROMPT_TEMPLATE.format(
        orb_high=orb.high, orb_low=orb.low,
        open=tc.open, close=tc.close, high=tc.high, low=tc.low,
        direction=trigger.direction.value,
        sl_distance=r_size, target_distance=r_size * 2,
    )

    image_bytes = base64.standard_b64decode(image_b64)
    response = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/png"), prompt],
        config=types.GenerateContentConfig(max_output_tokens=300, temperature=0.1),
    )

    raw = response.text.strip()
    start, end = raw.find("{"), raw.rfind("}") + 1
    return json.loads(raw[start:end])


# ---------------------------------------------------------------------------
# Robust OpenRouter Vision Call (Fixed)
# ---------------------------------------------------------------------------

def _call_openrouter_vision(cfg, image_b64: str, trigger: TriggerSetup, orb: OpeningRange) -> dict:
    """Robust OpenAI-compatible call to OpenRouter."""
    tc = trigger.trigger_candle
    r_size = abs(trigger.reference_level - trigger.sl_price)

    prompt = _PROMPT_TEMPLATE.format(
        orb_high=orb.high, orb_low=orb.low,
        open=tc.open, close=tc.close, high=tc.high, low=tc.low,
        direction=trigger.direction.value,
        sl_distance=r_size, target_distance=r_size * 2,
    )

    headers = {
        "Authorization": f"Bearer {cfg.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": cfg.get("openrouter_referer", "https://btc-orb-bot.com"),
        "X-Title": cfg.get("openrouter_title", "BTC ORB Bot"),
    }

    payload = {
        "model": cfg.openrouter_model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                }
            ]
        }],
        "temperature": 0.1,
        "max_tokens": 400,
    }

    response = requests.post(
        f"{cfg.openrouter_base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=35
    )

    if response.status_code != 200:
        logger.warning("OpenRouter HTTP %d: %s", response.status_code, response.text[:300])
        raise Exception(f"HTTP {response.status_code}")

    data = response.json()

    # Robust content extraction
    try:
        content = data["choices"][0]["message"]["content"]
        if not content or not isinstance(content, str):
            raise Exception("Empty or invalid content from OpenRouter")
    except (KeyError, TypeError, IndexError) as e:
        logger.warning("OpenRouter: Unexpected response structure - %s", e)
        raise Exception("Invalid response structure from OpenRouter")

    content = content.strip()

    # Extract JSON from response
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1 or end <= start:
        raise Exception("No valid JSON found in OpenRouter response")

    json_str = content[start:end]
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# Main AI Filter (Supports Both Providers)
# ---------------------------------------------------------------------------

def run_ai_filter(
    candles: list[Candle],
    trigger: TriggerSetup,
    orb: OpeningRange,
    cfg,
) -> dict:
    ts_str = now_ist().strftime("%Y%m%d_%H%M%S")
    direction = trigger.direction.value.lower()
    chart_path = str(Path(cfg.chart_image_path) / f"{ts_str}_{direction}.png")
    ai_log_path = str(Path(cfg.ai_log_path) / f"{ts_str}_{direction}.json")

    result = {
        "approved": True,
        "decision": cfg.ai_fallback_action.upper(),
        "confidence": 0,
        "reason": "ai_disabled_or_fallback",
        "chart_path": chart_path,
        "provider": "none"
    }

    try:
        # Generate chart
        lookback = candles[-cfg.chart_lookback_candles:] if len(candles) > cfg.chart_lookback_candles else candles
        generate_chart(lookback, orb, trigger, chart_path)

        image_b64 = base64.standard_b64encode(Path(chart_path).read_bytes()).decode()

        ai_resp = None

        # === Primary Provider ===
        if cfg.ai_provider == "openrouter" and getattr(cfg, "use_openrouter", False) and cfg.openrouter_api_key:
            logger.info("Using OpenRouter as primary provider")
            ai_resp = _call_openrouter_vision(cfg, image_b64, trigger, orb)
            result["provider"] = "openrouter"

        elif cfg.ai_provider == "gemini" and getattr(cfg, "use_gemini", True) and cfg.gemini_api_key:
            logger.info("Using Gemini as primary provider")
            ai_resp = _call_gemini_vision(
                cfg.gemini_api_key, image_b64, trigger, orb, cfg.ai_model
            )
            result["provider"] = "gemini"

        # === Fallback Logic ===
        if not ai_resp:
            if getattr(cfg, "use_openrouter", False) and cfg.openrouter_api_key and cfg.ai_provider != "openrouter":
                logger.info("Falling back to OpenRouter")
                ai_resp = _call_openrouter_vision(cfg, image_b64, trigger, orb)
                result["provider"] = "openrouter"
            elif getattr(cfg, "use_gemini", True) and cfg.gemini_api_key and cfg.ai_provider != "gemini":
                logger.info("Falling back to Gemini")
                ai_resp = _call_gemini_vision(
                    cfg.gemini_api_key, image_b64, trigger, orb, cfg.ai_model
                )
                result["provider"] = "gemini"

        # Process AI Response
        if ai_resp:
            decision = ai_resp.get("decision", "APPROVE").upper()
            confidence = int(ai_resp.get("confidence", 0))
            result.update({
                "decision": decision,
                "confidence": confidence,
                "reason": ai_resp.get("reason", "No reason provided"),
            })

            if cfg.ai_filter_mode == "active":
                result["approved"] = (decision == "APPROVE" and confidence >= cfg.ai_min_confidence)
            else:
                result["approved"] = True

    except Exception as exc:
        logger.warning("AI filter error: %s — fallback=%s", exc, cfg.ai_fallback_action)
        result["reason"] = f"error: {exc}"

    # Log AI decision
    try:
        Path(ai_log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(ai_log_path, "w") as f:
            json.dump({
                "timestamp": now_ist().isoformat(),
                "direction": trigger.direction.value,
                "mode": cfg.ai_filter_mode,
                "provider": result.get("provider"),
                **result,
            }, f, indent=2)
    except Exception as log_exc:
        logger.warning("AI log write failed: %s", log_exc)

    return result