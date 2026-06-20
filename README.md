# FinTwin — Agentic AI Financial Twin for Proactive Banking
**Dev Kumar Raikwar | SBI Hackathon 2024**

> FinTwin doesn't wait for customers to ask. It detects the moment their financial life changes — and acts first.

---

## What it does

FinTwin builds a Digital Financial Twin for every SBI customer by continuously monitoring transaction patterns. The moment a life event is detected — a salary jump, a new loan, a savings milestone — it autonomously identifies the right SBI product and generates a personalised outreach message.

## Project Structure

```
fintwin/
├── generate_data.py      # Synthetic transaction data generator (500 customers, 6 months)
├── detect_events.py      # Life event detection engine (salary jump, new EMI, savings milestone)
├── agent.py              # LLM reasoning agent — classify, match, message (Day 2)
├── main.py               # FastAPI backend (Day 2)
├── frontend/             # React dashboard (Day 3)
├── data/
│   ├── customers.json    # Generated customer profiles
│   ├── transactions.csv  # 40,000+ synthetic transactions
│   └── detected_events.json  # Detected life events with confidence scores
└── requirements.txt
```

## Day 1 — Running the detection engine

```bash
# Install dependencies
pip install -r requirements.txt

# Generate synthetic data
python generate_data.py

# Run life event detector
python detect_events.py
```

**Output:**
```
✓ 500 customers generated
✓ 41,185 transactions generated
✓ Life events injected: 185

FINTWIN — LIFE EVENT DETECTION RESULTS
Total events detected: 183
  — New Job / Salary Jump        75
  — New EMI / Loan               60
  — Savings Milestone            48
```

## Tech Stack

| Layer | Tech |
|---|---|
| Data Generation | Python, Faker, pandas |
| Event Detection | numpy, rule-based + statistical thresholds |
| Reasoning Agent | Claude API / GPT-4, LangChain (Day 2) |
| Backend | FastAPI (Day 2) |
| Frontend | React, Tailwind CSS (Day 3) |

## Problem Statement

SBI Hackathon — Problem Statement 3: Digital Engagement

---

*Built by Dev Kumar Raikwar*
