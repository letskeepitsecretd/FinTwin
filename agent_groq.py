"""
FinTwin — Day 2: AI Reasoning + Outreach Agent (Groq version)
------------------------------------------------------------------
Same as agent.py, but uses Groq's free API instead of Gemini.
Groq's free tier worked when this project's Gemini account hit a
hard "limit: 0" wall that wasn't fixable by waiting or retrying.

Setup:
    1. Get a free key at https://console.groq.com/keys (no card needed)
    2. In .env, add: GROQ_API_KEY=your_key_here
    3. pip3 install openai --break-system-packages   (Groq uses the
       OpenAI-compatible client, just pointed at a different URL)

Run:
    python3 agent_groq.py
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    sys.exit(
        "ERROR: GROQ_API_KEY not found.\n"
        "Get a free key at https://console.groq.com/keys and add to .env:\n"
        "  GROQ_API_KEY=your_key_here"
    )

client = OpenAI(api_key=API_KEY, base_url="https://api.groq.com/openai/v1")
MODEL_NAME = "llama-3.3-70b-versatile"

DATA_DIR = Path("data")
EVENTS_FILE = DATA_DIR / "detected_events.json"
CUSTOMERS_FILE = DATA_DIR / "customers.json"
OUTPUT_FILE = DATA_DIR / "recommendations.json"

# Groq's free tier is generous, but we still keep this modest and paced
# to stay safely within limits and keep the demo run fast.
MAX_CUSTOMERS = 15
SECONDS_BETWEEN_CALLS = 2
SECONDS_ON_RATE_LIMIT = 15


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
# Prompt construction (identical to the Gemini version)
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
# Groq call with retry + JSON cleanup
# ---------------------------------------------------------------------------

def call_groq(prompt: str, retries: int = 2) -> dict:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            text = response.choices[0].message.content.strip()
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
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                print(f"  [retry {attempt}/{retries}] Rate limit hit, waiting {SECONDS_ON_RATE_LIMIT}s...")
                time.sleep(SECONDS_ON_RATE_LIMIT)
            else:
                print(f"  [retry {attempt}/{retries}] API error: {e}")
                time.sleep(2)
    raise RuntimeError(f"Failed after {retries} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def pick_subset(events: list[dict], max_count: int) -> list[dict]:
    """Pick a small, varied subset: spread across different event types
    rather than just taking the first N."""
    by_type: dict[str, list[dict]] = {}
    for e in events:
        by_type.setdefault(e.get("event_type", "unknown"), []).append(e)

    types = list(by_type.keys())
    subset = []
    i = 0
    while len(subset) < max_count and any(by_type[t] for t in types):
        t = types[i % len(types)]
        if by_type[t]:
            subset.append(by_type[t].pop(0))
        i += 1
    return subset


def main():
    events = load_json(EVENTS_FILE)
    customers = load_json(CUSTOMERS_FILE)
    customer_index = index_customers_by_id(customers)

    subset = pick_subset(events, MAX_CUSTOMERS)
    print(f"Loaded {len(events)} total detected events.")
    print(f"Processing a demo subset of {len(subset)} (spread across event types).")
    print(f"Using model: {MODEL_NAME} via Groq\n")

    DATA_DIR.mkdir(exist_ok=True)
    results = []
    done_ids = set()
    if OUTPUT_FILE.exists():
        try:
            results = load_json(OUTPUT_FILE)
            done_ids = {r["customer_id"] for r in results}
            if done_ids:
                print(f"Found existing recommendations.json with {len(done_ids)} done — resuming.\n")
        except Exception:
            results = []

    def save():
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    for i, event in enumerate(subset, start=1):
        cust_id = event.get("customer_id")

        if cust_id in done_ids:
            print(f"[{i}/{len(subset)}] {cust_id}: already done, skipping")
            continue

        customer = customer_index.get(cust_id)
        if customer is None:
            print(f"[{i}/{len(subset)}] {cust_id}: SKIPPED (no matching customer profile)")
            continue

        print(f"[{i}/{len(subset)}] {cust_id} ({customer.get('name')}) — {event.get('event_label')}")

        prompt = build_prompt(event, customer)
        try:
            ai_result = call_groq(prompt)
        except Exception as e:
            print(f"  FAILED, skipping this customer: {e}")
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

        save()
        print(f"  Saved ({len(results)} total in recommendations.json)")

        time.sleep(SECONDS_BETWEEN_CALLS)

    save()
    print(f"\nDone. {len(results)} recommendations saved to {OUTPUT_FILE}")
    if len(results) < len(subset):
        print(f"Note: {len(subset) - len(results)} customers failed/skipped. Re-run the script to retry just those.")


if __name__ == "__main__":
    main()
