"""
Enhanced OpenRouter Vision Test Script (with better model suggestions)
"""

import os
import base64
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
import time

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Current working free vision models (as of May 2026)
MODELS_TO_TEST = [
    "openrouter/free",                          # Auto router - worth trying
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "moonshotai/kimi-vl-a3b-thinking:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

TEST_PROMPT = """You are a professional trading filter for BTC Opening Range Breakout strategy.
Analyze the candlestick chart and respond in valid JSON only.

{
  "decision": "APPROVE" or "REJECT",
  "confidence": <number 1-10>,
  "reason": "short explanation"
}
"""

def test_openrouter_vision():
    print("🔍 OpenRouter Vision Test (Chart Analysis)\n")

    if not OPENROUTER_API_KEY:
        print("❌ OPENROUTER_API_KEY missing in .env")
        return

    print(f"🔑 Key: {OPENROUTER_API_KEY[:25]}...\n")

    # Create test chart
    chart_path = Path("test_chart.png")
    if not chart_path.exists():
        print("📊 Creating test chart...")
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            plt.figure(figsize=(12, 7))
            x = np.linspace(0, 40, 100)
            plt.plot(x, 82000 + x*120, 'b-', label="BTC Price")
            plt.axhline(y=83500, color='green', linestyle='--', label="OR High")
            plt.axhline(y=81000, color='red', linestyle='--', label="OR Low")
            plt.title("BTC ORB Strategy - Test Chart")
            plt.legend()
            plt.grid(True)
            plt.savefig(chart_path)
            plt.close()
            print(f"✅ Chart created: {chart_path}")
        except Exception as e:
            print(f"Chart creation failed: {e}")
            return

    with open(chart_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    print(f"📸 Image size: {len(image_b64)//1024} KB\n")

    for model in MODELS_TO_TEST:
        print(f"🔄 Trying: {model}")
        success = try_single_model(model, image_b64)
        if success:
            print(f"\n✅ Recommended model: **{model}**")
            print("Use this in config.py")
            return
        time.sleep(2)  # Small delay between attempts

    print("\n❌ All free models are rate-limited right now.")
    print("Recommendations:")
    print("1. Wait 5-15 minutes and try again")
    print("2. Add $5-10 credit on OpenRouter (greatly increases limits)")
    print("3. Switch back to Gemini when quota resets")


def try_single_model(model: str, image_b64: str):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://btc-orb-bot.com",
        "X-Title": "BTC ORB Bot",
    }

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": TEST_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
            ]
        }],
        "temperature": 0.1,
        "max_tokens": 400,
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=40
        )

        print(f"   → Status: {response.status_code}")

        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"].strip()
            print("   ✅ SUCCESS!")
            print("   Sample response:", content[:300] + "..." if len(content) > 300 else content)
            return True
        else:
            try:
                err = response.json()
                print("   Error:", err.get("error", {}).get("message", response.text[:200]))
            except:
                print("   Raw:", response.text[:300])
            return False

    except Exception as e:
        print(f"   Exception: {e}")
        return False


if __name__ == "__main__":
    test_openrouter_vision()