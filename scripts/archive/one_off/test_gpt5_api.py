#!/usr/bin/env python3
"""Test GPT-5-mini API"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load .env
load_dotenv(Path(__file__).parent.parent / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

print("Testing GPT-5-mini API...")
print(f"API Key loaded: {bool(os.getenv('OPENAI_API_KEY'))}")

try:
    response = client.responses.create(
        model="gpt-5-mini",
        input="Classify this email: From: Amazon, Subject: Your order has shipped",
        reasoning={"effort": "low"},
        text={"verbosity": "low"},
    )
    print("✅ GPT-5-mini SUCCESS!")
    print(f"Output: {response.output_text}")
except Exception as e:
    print(f"❌ GPT-5-mini ERROR: {e}")
    print(f"Error type: {type(e).__name__}")
