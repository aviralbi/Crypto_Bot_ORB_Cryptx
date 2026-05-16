"""
AI Vision Filter — Gemini + OpenRouter (Production Ready)
"""

import base64
import json
from pathlib import Path

import requests

from google import genai
from google.genai import types

from models import Candle, TriggerSetup, OpeningRange, Direction
from utils import get_logger, now_ist

logger = get_logger("ai_filter")


# ---------------------------------------------------------------------------
# Chart Generation
# ---------------------------------------------------------------------------
def generate_chart(candles: list[Candle], orb: OpeningRange, trigger: TriggerSetup, save_path: str) -> str:
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
    df = pd.DataFrame(data, index=pd.DatetimeIndex([c.timestamp for c in candles]))

    add_plots = [
        mpf.make_addplot([orb.high] * len(candles), color="lime", linestyle="--", width=1.5),
        mpf.make_addplot([orb.low] * len(candles), color="tomato", linestyle="--", width=1.5),
    ]

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    style = mpf.make_mpf_style(base_mpf_style="charles", rc={"figure.figsize": (14, 7)})

    fig, axes = mpf.plot(df, type="candle", addplot=add_plots, style=style,
                         title=f"BTC ORB — {trigger.direction.value} Setup | OR H={orb.high:.0f} L={orb.low:.0f}",
                         volume=True, returnfig=True)

    # Mark trigger candle
    trigger_idx = next((i for i, c in enumerate(candles) if c.timestamp == trigger.trigger_candle.timestamp), None)
    if trigger_idx is not None:
        ax = axes[0]
        ax.axvline(x=trigger_idx, color="orange", linewidth=2, alpha=0.8)

    fig.savefig(save_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", save_path)
    return save_path


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
_PROMPT_TEMPLATE = """You are a professional trading filter for BTC ORB strategy.
Analyze the chart and respond **only** in valid JSON:

{
  "decision": "APPROVE" or "REJECT",
  "confidence": <1-10>,
  "reason": "short reason"
}"""


# ---------------------------------------------------------------------------
# Gemini Call
# ---------------------------------------------------------------------------
def _call_gemini_vision(api_key: str, image_b64: str, trigger: TriggerSetup, orb: OpeningRange, model: str) -> dict:
    # ... (keep your existing Gemini function)
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
# Robust OpenRouter Call
# ---------------------------------------------------------------------------
def _call_openrouter_vision(cfg, image_b64: str, trigger: TriggerSetup, orb: OpeningRange) -> dict:
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
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
            ]
        }],
        "temperature": 0.1,
        "max_tokens": 600,
    }

    response = requests.post(
        f"{cfg.openrouter_base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=45
    )

    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}")

    data = response.json()
    message = data["choices"][0]["message"]

    # Handle both content and reasoning fields
    final_text = message.get("content") or message.get("reasoning") or ""
    final_text = str(final_text).strip()

    if not final_text:
        raise Exception("Model returned empty response")

    # Extract JSON
    start = final_text.find("{")
    end = final_text.rfind("}") + 1
    if start == -1 or end <= start:
        raise Exception("No JSON found in response")

    return json.loads(final_text[start:end])


# ---------------------------------------------------------------------------
# Main Function with Improved Logging
# ---------------------------------------------------------------------------
def run_ai_filter(candles: list[Candle], trigger: TriggerSetup, orb: OpeningRange, cfg) -> dict:
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
        lookback = candles[-cfg.chart_lookback_candles:] if len(candles) > cfg.chart_lookback_candles else candles
        generate_chart(lookback, orb, trigger, chart_path)

        image_b64 = base64.standard_b64encode(Path(chart_path).read_bytes()).decode()

        logger.info("AI Filter: Sending chart to %s for %s trigger", cfg.ai_provider, direction.upper())

        ai_resp = None

        if cfg.ai_provider == "openrouter" and getattr(cfg, "use_openrouter", False) and cfg.openrouter_api_key:
            ai_resp = _call_openrouter_vision(cfg, image_b64, trigger, orb)
            result["provider"] = "openrouter"
        elif cfg.ai_provider == "gemini" and getattr(cfg, "use_gemini", True) and cfg.gemini_api_key:
            ai_resp = _call_gemini_vision(cfg.gemini_api_key, image_b64, trigger, orb, cfg.ai_model)
            result["provider"] = "gemini"

        if ai_resp:
            decision = str(ai_resp.get("decision", "APPROVE")).upper()
            confidence = int(ai_resp.get("confidence", 5))
            reason = ai_resp.get("reason", "")

            result.update({
                "decision": decision,
                "confidence": confidence,
                "reason": reason,
            })

            if cfg.ai_filter_mode == "active":
                result["approved"] = (decision == "APPROVE" and confidence >= cfg.ai_min_confidence)
            else:
                result["approved"] = True

            logger.info("AI %s → %s | Confidence=%d | Reason: %s", 
                       result["provider"].upper(), decision, confidence, reason[:100])

    except Exception as exc:
        logger.warning("AI filter error: %s — fallback=%s", exc, cfg.ai_fallback_action)
        result["reason"] = f"error: {exc}"

    # Save log
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
    except Exception as e:
        logger.warning("Failed to write AI log: %s", e)

    return result