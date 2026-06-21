"""Minimal Groq quota check — uses almost no tokens, just confirms the key works right now."""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
key = os.getenv("GROQ_API_KEY")

if not key:
    print("No GROQ_API_KEY found in .env")
else:
    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        print("SUCCESS — quota is available:", r.choices[0].message.content)
    except Exception as e:
        print("STILL BLOCKED:", e)
