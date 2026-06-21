"""Quick test: confirms GEMINI_API_KEY in .env actually works."""
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
key = os.getenv("GEMINI_API_KEY")

if not key:
    print("No GEMINI_API_KEY found in .env")
else:
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    try:
        r = model.generate_content("Say hello in 5 words.")
        print("SUCCESS:", r.text)
    except Exception as e:
        print("FAILED:", e)
