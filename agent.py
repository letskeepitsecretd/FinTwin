"""
FinTwin — Day 2: AI Reasoning + Outreach Agent
------------------------------------------------
Day 1 already does deterministic detection + rule-based product mapping
(detect_events.py -> data/detected_events.json).

Day 2 adds the AI layer on top of that:
  1. For each detected event, pull the full customer profile.
  2. Ask Gemini to explain WHY the recommended product(s) fit this specific
     customer (using their real numbers), and to draft a short, personalized
     SMS/email a relationship manager (RM) could send to the customer.
  3. Save everything to data/recommendations.json for the Streamlit dashboard.

Run:
    python3 agent.py
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import google.generativeai as genai

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    sys.exit(
        "ERROR: GEMINI_API_KEY not found.\n"
        "Make sure you have a .env file in this folder with:\n"
        "  GEMINI_API_KEY=your_key_here"
    )

genai.configure(api_key=API_KEY)
MODEL_NAME = "gemini-2.0-flash"
model = genai.GenerativeModel(MODEL_NAME)

DATA_DIR = Path("data")
EVENTS_FILE = DATA_DIR / "detected_events.json"
CUSTOMERS_FILE = DATA_DIR / "customers.json"
OUTPUT_FILE = DATA_DIR / "recommendations.json"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_json(path: Path):
    if not path.exists():
        sys.exit(f"ERROR: {path} not found. Run Day 1 scripts first.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def index_customers_by_id(customers: list[dict]) -> dict:
    return {c["customer_id"]: c for c in customers}


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """You are an AI assistant for SBI (State Bank of India) relationship managers.

A customer life event has just been detected by our system. Your job is to:
1. Explain briefly WHY each recommended product fits this specific customer's situation (use their actual numbers, not generic language).
2. Draft a short, warm, personalized SMS/email message that the relationship manager can send DIRECTLY to the customer, inviting them to take the next step. It should NOT sound like spam or a generic bank promo — reference their actual situation naturally.
3. Suggest a priority level for the RM's outreach queue.

CUSTOMER PROFILE:
- Name: {name}
- Age: {age}
- City: {city}
- Base salary: ₹{base_salary}
- Savings balance: ₹{savings_balance}
- Has existing EMI: {has_emi}
- Existing EMI amount: ₹{existing_emi_amount}

DETECTED EVENT:
- Type: {event_label}
- Signal: {signal}
- Detected in month: {detected_month}
- Confidence: {confidence}

CANDIDATE PRODUCTS (already selected by our rules engine):
{products_list}

Respond ONLY with valid JSON in exactly this shape, no markdown fences, no preamble:
{{
  "reasoning": "2-3 sentences explaining why these products fit, using the customer's real numbers",
  "priority": "high | medium | low",
  "priority_reason": "one short sentence",
  "outreach_message": {{
    "channel": "sms | email",
    "subject": "only if channel is email, else empty string",
    "body": "the actual message text, personalized, max 400 characters, no placeholders like [Name] — use their real name"
  }}
}}
"""


def build_prompt(event: dict, customer: dict) -> str:
    products_list = "\n".join(
        f"- {p['name']} ({p['type']})" for p in event.get("recommended_products", [])
    )
    return PROMPT_TEMPLATE.format(
        name=customer.get("name", event.get("customer_name", "the customer")),
        age=customer.get("age", "unknown"),
        city=customer.get("city", "unknown"),
        base_salary=customer.get("base_salary", "unknown"),
        savings_balance=customer.get("savings_balance", "unknown"),
        has_emi=customer.get("has_emi", "unknown"),
        existing_emi_amount=customer.get("existing_emi_amount", 0),
        event_label=event.get("event_label", event.get("event_type", "")),
        signal=event.get("signal", ""),
        detected_month=event.get("detected_month", ""),
        confidence=event.get("confidence", ""),
        products_list=products_list or "- General relationship check-in",
    )


# ---------------------------------------------------------------------------
# Gemini call with basic retry + JSON cleanup
# ---------------------------------------------------------------------------

def call_gemini(prompt: str, retries: int = 3) -> dict:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            # Strip accidental markdown fences if the model adds them anyway
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_err = e
            print(f"  [retry {attempt}/{retries}] Bad JSON from model, retrying...")
            time.sleep(1.5)
        except Exception as e:
            last_err = e
            print(f"  [retry {attempt}/{retries}] API error: {e}")
            time.sleep(2)
    raise RuntimeError(f"Failed after {retries} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    events = load_json(EVENTS_FILE)
    customers = load_json(CUSTOMERS_FILE)
    customer_index = index_customers_by_id(customers)

    print(f"Loaded {len(events)} detected events, {len(customers)} customers.")
    print(f"Using model: {MODEL_NAME}\n")

    results = []
    for i, event in enumerate(events, start=1):
        cust_id = event.get("customer_id")
        customer = customer_index.get(cust_id)

        if customer is None:
            print(f"[{i}/{len(events)}] {cust_id}: SKIPPED (no matching customer profile)")
            continue

        print(f"[{i}/{len(events)}] {cust_id} ({customer.get('name')}) — {event.get('event_label')}")

        prompt = build_prompt(event, customer)
        try:
            ai_result = call_gemini(prompt)
        except Exception as e:
            print(f"  FAILED: {e}")
            continue

        results.append({
            "customer_id": cust_id,
            "customer_name": customer.get("name"),
            "event_type": event.get("event_type"),
            "event_label": event.get("event_label"),
            "signal": event.get("signal"),
            "confidence": event.get("confidence"),
            "recommended_products": event.get("recommended_products", []),
            "ai_reasoning": ai_result.get("reasoning"),
            "priority": ai_result.get("priority"),
            "priority_reason": ai_result.get("priority_reason"),
            "outreach": ai_result.get("outreach_message"),
        })

        # Gentle pacing to stay well within free-tier rate limits
        time.sleep(1)

    DATA_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(results)} recommendations saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
