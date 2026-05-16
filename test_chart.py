"""
OpenRouter Vision Test - Full Reasoning + Content Display
"""

import os
import base64
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

CHART_PATH = Path("logs/charts/20260516_124501_short.png")

TEST_PROMPT = """You are a trading filter for a BTC ORB (Opening Range Breakout) strategy.
Analyze the provided candlestick chart carefully and respond in valid JSON only.

{
  "decision": "APPROVE" or "REJECT",
  "confidence": integer between 1 and 10,
  "reason": "short clear reason"
}
"""

def test_with_specific_chart():
    print("🔍 OpenRouter Vision Test - Full Output\n")

    if not CHART_PATH.exists():
        print(f"❌ Chart not found: {CHART_PATH}")
        return

    with open(CHART_PATH, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://btc-orb-bot.com",
        "X-Title": "BTC ORB Bot Test",
    }

    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": TEST_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
            ]
        }],
        "temperature": 0.1,
        "max_tokens": 800,          # Increased
    }

    print("🚀 Sending chart to OpenRouter...\n")

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=45
        )

        print(f"📡 Status Code: {response.status_code}\n")

        if response.status_code != 200:
            print(response.text)
            return

        data = response.json()
        choice = data["choices"][0]["message"]

        print("📋 FULL RESPONSE FROM MODEL:\n")
        print("=" * 90)

        # Print reasoning (this model puts thinking here)
        if choice.get("reasoning"):
            print("🧠 REASONING:")
            print(choice["reasoning"])
            print("-" * 90)

        # Print content
        content = choice.get("content")
        if content:
            print("📝 CONTENT:")
            print(content)
        else:
            print("⚠️  Content field is NULL")

        print("=" * 90)

        # Try JSON parsing if content exists
        if content and isinstance(content, str):
            try:
                parsed = json.loads(content.strip())
                print(f"\n✅ Parsed JSON:")
                print(f"Decision   : {parsed.get('decision')}")
                print(f"Confidence : {parsed.get('confidence')}")
                print(f"Reason     : {parsed.get('reason')}")
            except:
                print("Could not parse as JSON")

    except Exception as e:
        print(f"❌ Exception: {e}")


if __name__ == "__main__":
    test_with_specific_chart()