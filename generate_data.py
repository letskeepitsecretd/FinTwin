"""
FinTwin — Synthetic Transaction Data Generator
Dev Kumar Raikwar

Generates realistic Indian banking transaction data for 500 customers
over 6 months. Injects life events (salary jump, new EMI, savings milestone)
into random customers so the detector has real signals to find.
"""

import pandas as pd
import numpy as np
import json
import random
from faker import Faker
from datetime import datetime, timedelta

fake = Faker("en_IN")
random.seed(42)
np.random.seed(42)

# ---------- Config ----------
NUM_CUSTOMERS = 500
MONTHS = 6
START_DATE = datetime(2024, 1, 1)
OUTPUT_CUSTOMERS = "data/customers.json"
OUTPUT_TRANSACTIONS = "data/transactions.csv"

# Life event injection rates (% of customers)
SALARY_JUMP_RATE = 0.15      # 15% get a new job mid-simulation
NEW_EMI_RATE = 0.12          # 12% take a new loan
SAVINGS_MILESTONE_RATE = 0.10 # 10% hit a savings milestone

import os
os.makedirs("data", exist_ok=True)


# ---------- Customer profiles ----------
def generate_customers(n):
    customers = []
    salary_brackets = [
        (18000, 30000),   # entry level
        (30000, 60000),   # mid level
        (60000, 120000),  # senior
        (120000, 250000), # lead / manager
    ]
    weights = [0.4, 0.35, 0.2, 0.05]

    for i in range(n):
        bracket = random.choices(salary_brackets, weights=weights)[0]
        base_salary = random.randint(*bracket)
        age = random.randint(22, 55)

        customers.append({
            "customer_id": f"SBI{10000 + i}",
            "name": fake.name(),
            "age": age,
            "city": random.choice(["Mumbai", "Delhi", "Bengaluru", "Chennai",
                                   "Hyderabad", "Pune", "Kolkata", "Ahmedabad",
                                   "Lucknow", "Jaipur"]),
            "base_salary": base_salary,
            "savings_balance": random.randint(5000, base_salary * 4),
            "has_emi": random.choice([True, False]),
            "existing_emi_amount": random.randint(3000, 25000) if random.random() < 0.4 else 0,
            # life event flags — injected below
            "life_event": None,
            "life_event_month": None,
        })

    # Inject life events
    customer_ids = list(range(n))

    # Salary jump — new job
    jump_ids = random.sample(customer_ids, int(n * SALARY_JUMP_RATE))
    for idx in jump_ids:
        customers[idx]["life_event"] = "salary_jump"
        customers[idx]["life_event_month"] = random.randint(2, 5)
        old = customers[idx]["base_salary"]
        customers[idx]["new_salary"] = int(old * random.uniform(1.4, 2.8))

    # New EMI — loan taken
    remaining = [i for i in customer_ids if customers[i]["life_event"] is None]
    emi_ids = random.sample(remaining, int(n * NEW_EMI_RATE))
    for idx in emi_ids:
        customers[idx]["life_event"] = "new_emi"
        customers[idx]["life_event_month"] = random.randint(2, 5)
        customers[idx]["new_emi_amount"] = random.randint(8000, 40000)

    # Savings milestone
    remaining = [i for i in customer_ids if customers[i]["life_event"] is None]
    sav_ids = random.sample(remaining, int(n * SAVINGS_MILESTONE_RATE))
    for idx in sav_ids:
        customers[idx]["life_event"] = "savings_milestone"
        customers[idx]["life_event_month"] = random.randint(2, 5)
        customers[idx]["milestone_amount"] = random.choice([100000, 200000, 500000])

    return customers


# ---------- Transaction generator ----------
def generate_transactions(customers):
    rows = []
    categories = ["groceries", "utilities", "dining", "travel",
                  "shopping", "medical", "entertainment", "fuel"]

    for c in customers:
        cid = c["customer_id"]
        salary = c["base_salary"]
        event = c["life_event"]
        event_month = c.get("life_event_month", None)

        # Generate month by month
        for month_offset in range(MONTHS):
            month_date = START_DATE + timedelta(days=30 * month_offset)
            month_num = month_offset + 1

            # Effective salary this month
            if event == "salary_jump" and event_month and month_num >= event_month:
                effective_salary = c["new_salary"]
            else:
                effective_salary = salary

            # Salary credit (1st of month)
            rows.append({
                "customer_id": cid,
                "date": month_date.strftime("%Y-%m-%d"),
                "type": "credit",
                "category": "salary",
                "amount": effective_salary + random.randint(-500, 500),
                "description": "SALARY CREDIT",
                "month": month_num,
            })

            # Savings deposit (random amount, higher if milestone approaching)
            if event == "savings_milestone" and event_month and month_num >= event_month:
                sav_amount = int(effective_salary * random.uniform(0.3, 0.5))
            else:
                sav_amount = int(effective_salary * random.uniform(0.05, 0.2))

            rows.append({
                "customer_id": cid,
                "date": (month_date + timedelta(days=2)).strftime("%Y-%m-%d"),
                "type": "credit",
                "category": "savings_transfer",
                "amount": sav_amount,
                "description": "SELF TRANSFER TO SAVINGS",
                "month": month_num,
            })

            # EMI debit
            if c["has_emi"] and c["existing_emi_amount"] > 0:
                rows.append({
                    "customer_id": cid,
                    "date": (month_date + timedelta(days=5)).strftime("%Y-%m-%d"),
                    "type": "debit",
                    "category": "emi",
                    "amount": c["existing_emi_amount"] + random.randint(-200, 200),
                    "description": "EMI PAYMENT",
                    "month": month_num,
                })

            # New EMI injection
            if event == "new_emi" and event_month and month_num >= event_month:
                rows.append({
                    "customer_id": cid,
                    "date": (month_date + timedelta(days=5)).strftime("%Y-%m-%d"),
                    "type": "debit",
                    "category": "emi",
                    "amount": c["new_emi_amount"] + random.randint(-300, 300),
                    "description": "LOAN EMI PAYMENT",
                    "month": month_num,
                })

            # Daily spending transactions (8-15 per month)
            num_txns = random.randint(8, 15)
            for _ in range(num_txns):
                cat = random.choice(categories)
                spend_range = {
                    "groceries": (500, 4000),
                    "utilities": (200, 1500),
                    "dining": (200, 2000),
                    "travel": (300, 5000),
                    "shopping": (500, 8000),
                    "medical": (200, 3000),
                    "entertainment": (200, 2000),
                    "fuel": (500, 3000),
                }.get(cat, (200, 2000))

                txn_date = month_date + timedelta(days=random.randint(1, 28))
                rows.append({
                    "customer_id": cid,
                    "date": txn_date.strftime("%Y-%m-%d"),
                    "type": "debit",
                    "category": cat,
                    "amount": random.randint(*spend_range),
                    "description": f"{cat.upper()} PURCHASE",
                    "month": month_num,
                })

    df = pd.DataFrame(rows)
    df = df.sort_values(["customer_id", "date"]).reset_index(drop=True)
    return df


# ---------- Main ----------
if __name__ == "__main__":
    print("Generating customers...")
    customers = generate_customers(NUM_CUSTOMERS)

    print("Saving customer profiles...")
    with open(OUTPUT_CUSTOMERS, "w") as f:
        json.dump(customers, f, indent=2)

    print("Generating transactions...")
    df = generate_transactions(customers)
    df.to_csv(OUTPUT_TRANSACTIONS, index=False)

    # Quick summary
    events = [c for c in customers if c["life_event"]]
    print(f"\n✓ {NUM_CUSTOMERS} customers generated")
    print(f"✓ {len(df):,} transactions generated")
    print(f"✓ Life events injected: {len(events)}")
    print(f"  — salary_jump:        {sum(1 for c in events if c['life_event'] == 'salary_jump')}")
    print(f"  — new_emi:            {sum(1 for c in events if c['life_event'] == 'new_emi')}")
    print(f"  — savings_milestone:  {sum(1 for c in events if c['life_event'] == 'savings_milestone')}")
    print(f"\nData saved to data/")
