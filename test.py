"""
Simple OpenRouter API Connectivity Test
Just sends a basic "hello" prompt - No image required.
"""

import os
import json
import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()

# ================== CONFIG ==================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "openrouter/free"        # You can change this to a specific model

PROMPT = "Hello! Please respond with a short friendly message and the current date."
# ===========================================


def test_openrouter_connection():
    print("🔍 OpenRouter Simple Connectivity Test\n")

    if not OPENROUTER_API_KEY:
        print("❌ ERROR: OPENROUTER_API_KEY not found in .env file!")
        print("   Please add it and try again.")
        return

    if not OPENROUTER_API_KEY.startswith("sk-or-"):
        print("⚠️  Warning: API key doesn't start with 'sk-or-'. Please check it.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://btc-orb-bot.com",
        "X-Title": "BTC ORB Bot - Connection Test",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": PROMPT}
        ],
        "temperature": 0.7,
        "max_tokens": 150,
    }

    print(f"📡 Sending test request to model: {MODEL}...")

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=20
        )

        print(f"\n📡 Status Code: {response.status_code}")

        if response.status_code == 200:
            print("✅ SUCCESS! OpenRouter connection is working.\n")
            data = response.json()
            reply = data["choices"][0]["message"]["content"].strip()
            
            print("🤖 Response from OpenRouter:")
            print("-" * 60)
            print(reply)
            print("-" * 60)
            
            print("\n🎯 Test Completed Successfully!")
            
        else:
            print("❌ FAILED")
            print(f"Error: {response.text[:500]}")

    except requests.exceptions.Timeout:
        print("❌ Request timed out. Check your internet connection.")
    except Exception as e:
        print(f"❌ Exception occurred: {e}")


if __name__ == "__main__":
    test_openrouter_connection()