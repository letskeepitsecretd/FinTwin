"""
FinTwin — Live Transaction Feed & Simulator
-------------------------------------------
Generates continuous realistic transactions for existing customers,
injects new life events, runs the detection rules, and handles
interaction with the agent pipeline.
"""

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

from detect_events import detect_customer_events, SBI_PRODUCTS

TRANSACTIONS_FILE = Path("data/transactions.csv")
CUSTOMERS_FILE = Path("data/customers.json")

SPEND_RANGES = {
    "groceries": (500, 4000),
    "utilities": (200, 1500),
    "dining": (200, 2000),
    "travel": (300, 5000),
    "shopping": (500, 8000),
    "medical": (200, 3000),
    "entertainment": (200, 2000),
    "fuel": (500, 3000),
}


class TransactionSimulator:
    def __init__(self):
        self.customers = {}
        self.customer_states = {}
        self.df_txns = None
        self.load_initial_data()

    def load_initial_data(self):
        # Load customers
        if CUSTOMERS_FILE.exists():
            with open(CUSTOMERS_FILE, "r", encoding="utf-8") as f:
                customers_list = json.load(f)
                self.customers = {c["customer_id"]: c for c in customers_list}
        else:
            raise FileNotFoundError(f"{CUSTOMERS_FILE} not found.")

        # Load transactions
        if TRANSACTIONS_FILE.exists():
            self.df_txns = pd.read_csv(TRANSACTIONS_FILE)
        else:
            # Create empty df with schema if file does not exist
            self.df_txns = pd.DataFrame(columns=[
                "customer_id", "date", "type", "category", "amount", "description", "month"
            ])

        # Initialize customer states based on history
        for cid, c in self.customers.items():
            df_cust = self.df_txns[self.df_txns["customer_id"] == cid]
            if not df_cust.empty:
                # Find latest transaction
                df_cust_sorted = df_cust.sort_values("date")
                latest_txn = df_cust_sorted.iloc[-1]
                latest_date_str = latest_txn["date"]
                try:
                    latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")
                except ValueError:
                    latest_date = datetime(2024, 6, 28)
                latest_month = int(latest_txn["month"])
            else:
                latest_date = datetime(2024, 1, 1)
                latest_month = 1

            self.customer_states[cid] = {
                "last_date": latest_date,
                "last_month": latest_month,
                "pending_transactions": [],
                "active_new_emi": False,
                "new_emi_amount": 0,
                "injected_event_type": None,
            }

    def get_cumulative_savings(self, cid):
        df_cust = self.df_txns[self.df_txns["customer_id"] == cid]
        sav = df_cust[df_cust["category"] == "savings_transfer"]
        return sav["amount"].sum()

    def generate_next_transaction(self, cid):
        state = self.customer_states[cid]
        c = self.customers[cid]

        # 1. Process pending transactions if queue is not empty
        if state["pending_transactions"]:
            txn = state["pending_transactions"].pop(0)
            state["last_date"] = datetime.strptime(txn["date"], "%Y-%m-%d")
            state["last_month"] = int(txn["month"])
            self.append_transaction(txn)
            return txn

        # 2. Advance time
        next_date = state["last_date"] + timedelta(days=random.randint(1, 3))
        month_changed = next_date.month != state["last_date"].month

        if month_changed:
            next_month = state["last_month"] + 1
            state["last_month"] = next_month
            
            event_type = None
            if random.random() < 0.15:
                event_type = random.choice(["salary_jump", "new_emi", "savings_milestone"])
                state["injected_event_type"] = event_type
            
            monthly_txns = []

            # A. Salary Credit on the 1st
            sal_date = datetime(next_date.year, next_date.month, 1)
            if event_type == "salary_jump":
                sal_amount = int(c["base_salary"] * random.uniform(1.4, 1.8))
                desc = "SALARY CREDIT - PROMOTION"
            else:
                sal_amount = c["base_salary"] + random.randint(-500, 500)
                desc = "SALARY CREDIT"
            
            monthly_txns.append({
                "customer_id": cid,
                "date": sal_date.strftime("%Y-%m-%d"),
                "type": "credit",
                "category": "salary",
                "amount": sal_amount,
                "description": desc,
                "month": next_month
            })

            # B. Savings Transfer on the 2nd
            sav_date = datetime(next_date.year, next_date.month, 2)
            if event_type == "savings_milestone":
                curr_savings = self.get_cumulative_savings(cid)
                milestones = [100000, 200000, 500000]
                target_m = 100000
                for m in milestones:
                    if curr_savings < m:
                        target_m = m
                        break
                else:
                    target_m = int(curr_savings + 100000)
                
                sav_amount = max(15000, target_m - curr_savings + random.randint(1000, 5000))
                desc = "SELF TRANSFER - MILESTONE DEPOSIT"
            else:
                sav_amount = int(c["base_salary"] * random.uniform(0.05, 0.2))
                desc = "SELF TRANSFER TO SAVINGS"

            monthly_txns.append({
                "customer_id": cid,
                "date": sav_date.strftime("%Y-%m-%d"),
                "type": "credit",
                "category": "savings_transfer",
                "amount": sav_amount,
                "description": desc,
                "month": next_month
            })

            # C. Regular EMI Debit on the 5th
            if c["has_emi"] and c["existing_emi_amount"] > 0:
                emi_date = datetime(next_date.year, next_date.month, 5)
                monthly_txns.append({
                    "customer_id": cid,
                    "date": emi_date.strftime("%Y-%m-%d"),
                    "type": "debit",
                    "category": "emi",
                    "amount": c["existing_emi_amount"] + random.randint(-200, 200),
                    "description": "EMI PAYMENT",
                    "month": next_month
                })

            # D. New EMI Debit on the 5th
            if event_type == "new_emi" or state["active_new_emi"]:
                if event_type == "new_emi":
                    state["active_new_emi"] = True
                    state["new_emi_amount"] = random.randint(8000, 25000)
                
                emi_date = datetime(next_date.year, next_date.month, 5)
                monthly_txns.append({
                    "customer_id": cid,
                    "date": emi_date.strftime("%Y-%m-%d"),
                    "type": "debit",
                    "category": "emi",
                    "amount": state["new_emi_amount"] + random.randint(-300, 300),
                    "description": "LOAN EMI PAYMENT",
                    "month": next_month
                })

            # Sort queue by date ascending
            monthly_txns.sort(key=lambda x: x["date"])
            state["pending_transactions"] = monthly_txns

            # Pop the first one immediately
            txn = state["pending_transactions"].pop(0)
            state["last_date"] = datetime.strptime(txn["date"], "%Y-%m-%d")
            self.append_transaction(txn)
            return txn

        # 3. Generate a standard spending transaction
        cat = random.choice(list(SPEND_RANGES.keys()))
        spend_range = SPEND_RANGES[cat]
        amount = random.randint(*spend_range)
        txn = {
            "customer_id": cid,
            "date": next_date.strftime("%Y-%m-%d"),
            "type": "debit",
            "category": cat,
            "amount": amount,
            "description": f"{cat.upper()} PURCHASE",
            "month": state["last_month"]
        }
        state["last_date"] = next_date
        self.append_transaction(txn)
        return txn

    def append_transaction(self, txn):
        # 1. Append to CSV
        file_exists = TRANSACTIONS_FILE.exists()
        with open(TRANSACTIONS_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "customer_id", "date", "type", "category", "amount", "description", "month"
            ])
            if not file_exists:
                writer.writeheader()
            writer.writerow(txn)

        # 2. Update in-memory DataFrame
        new_row = pd.DataFrame([txn])
        self.df_txns = pd.concat([self.df_txns, new_row], ignore_index=True)

    def check_events_for_customer(self, cid):
        df_cust = self.df_txns[self.df_txns["customer_id"] == cid]
        c = self.customers[cid]
        return detect_customer_events(df_cust, c)

    def force_month_transition_with_event(self, cid, event_type):
        state = self.customer_states[cid]
        c = self.customers[cid]

        # Force transition to the next month
        next_month = state["last_month"] + 1
        state["last_month"] = next_month
        
        # Set next_date to the 1st of the new month safely
        last_date = state["last_date"]
        if last_date.month == 12:
            next_date = datetime(last_date.year + 1, 1, 1)
        else:
            next_date = datetime(last_date.year, last_date.month + 1, 1)
            
        state["last_date"] = next_date
        state["injected_event_type"] = event_type
        
        monthly_txns = []

        # A. Salary Credit on the 1st
        sal_date = datetime(next_date.year, next_date.month, 1)
        if event_type == "salary_jump":
            sal_amount = int(c["base_salary"] * random.uniform(1.45, 1.85))
            desc = "SALARY CREDIT - PROMOTION"
        else:
            sal_amount = c["base_salary"] + random.randint(-500, 500)
            desc = "SALARY CREDIT"
        
        monthly_txns.append({
            "customer_id": cid,
            "date": sal_date.strftime("%Y-%m-%d"),
            "type": "credit",
            "category": "salary",
            "amount": sal_amount,
            "description": desc,
            "month": next_month
        })

        # B. Savings Transfer on the 2nd
        sav_date = datetime(next_date.year, next_date.month, 2)
        if event_type == "savings_milestone":
            curr_savings = self.get_cumulative_savings(cid)
            milestones = [100000, 200000, 500000]
            target_m = 100000
            for m in milestones:
                if curr_savings < m:
                    target_m = m
                    break
            else:
                target_m = int(curr_savings + 100000)
            
            sav_amount = max(15000, target_m - curr_savings + random.randint(1000, 5000))
            desc = "SELF TRANSFER - MILESTONE DEPOSIT"
        else:
            sav_amount = int(c["base_salary"] * random.uniform(0.05, 0.2))
            desc = "SELF TRANSFER TO SAVINGS"

        monthly_txns.append({
            "customer_id": cid,
            "date": sav_date.strftime("%Y-%m-%d"),
            "type": "credit",
            "category": "savings_transfer",
            "amount": sav_amount,
            "description": desc,
            "month": next_month
        })

        # C. Regular EMI Debit on the 5th
        if c["has_emi"] and c["existing_emi_amount"] > 0:
            emi_date = datetime(next_date.year, next_date.month, 5)
            monthly_txns.append({
                "customer_id": cid,
                "date": emi_date.strftime("%Y-%m-%d"),
                "type": "debit",
                "category": "emi",
                "amount": c["existing_emi_amount"] + random.randint(-200, 200),
                "description": "EMI PAYMENT",
                "month": next_month
            })

        # D. New EMI Debit on the 5th
        if event_type == "new_emi" or state["active_new_emi"]:
            if event_type == "new_emi":
                state["active_new_emi"] = True
                state["new_emi_amount"] = random.randint(8000, 25000)
            
            emi_date = datetime(next_date.year, next_date.month, 5)
            monthly_txns.append({
                "customer_id": cid,
                "date": emi_date.strftime("%Y-%m-%d"),
                "type": "debit",
                "category": "emi",
                "amount": state["new_emi_amount"] + random.randint(-300, 300),
                "description": "LOAN EMI PAYMENT",
                "month": next_month
            })

        # Sort queue by date ascending
        monthly_txns.sort(key=lambda x: x["date"])
        state["pending_transactions"] = monthly_txns

        # Pop the first one immediately
        txn = state["pending_transactions"].pop(0)
        state["last_date"] = datetime.strptime(txn["date"], "%Y-%m-%d")
        self.append_transaction(txn)
        return txn



if __name__ == "__main__":
    print("Testing Transaction Simulator...")
    sim = TransactionSimulator()
    print("Loaded simulator.")
    
    # Pick a random customer and generate 25 transactions for them
    cid = random.choice(list(sim.customers.keys()))
    customer = sim.customers[cid]
    print(f"\nSelected customer: {customer['name']} ({cid})")
    
    print("Generating transactions:")
    for i in range(25):
        txn = sim.generate_next_transaction(cid)
        print(f"  Txn {i+1}: {txn['date']} | {txn['type']} | {txn['category']:<18} | ₹{txn['amount']:>6} | {txn['description']}")
        
    events = sim.check_events_for_customer(cid)
    if events:
        print(f"\n✓ Detected {len(events)} events:")
        for e in events:
            print(f"  — {e['event_label']}: {e['signal']} (confidence {e['confidence']*100:.0f}%)")
    else:
        print("\nNo events detected.")
