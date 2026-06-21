"""
FinTwin — SQLite Migration Script
---------------------------------
One-time script to read existing customer, event, and agent run JSON files,
and migrate them into the structured SQLite database.
"""

import json
import sys
from pathlib import Path
from db import init_db, insert_customer, insert_event, insert_agent_run, get_connection

CUSTOMERS_FILE = Path("data/customers.json")
EVENTS_FILE = Path("data/detected_events.json")
RUNS_FILE = Path("data/agent_runs.json")

def load_json(path: Path):
    if not path.exists():
        print(f"[Warning] File {path} not found. Skipping.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def migrate():
    print("=== FinTwin SQLite Migration ===")
    
    # 1. Initialize DB tables
    init_db()
    
    # 2. Load JSON files
    customers = load_json(CUSTOMERS_FILE)
    events = load_json(EVENTS_FILE)
    runs = load_json(RUNS_FILE)
    
    print(f"Loaded from disk:")
    print(f"  - {len(customers)} customers")
    print(f"  - {len(events)} events")
    print(f"  - {len(runs)} agent runs")
    
    # 3. Migrate Customers
    migrated_customers = 0
    for c in customers:
        try:
            insert_customer(c)
            migrated_customers += 1
        except Exception as e:
            print(f"[Error] Failed to insert customer {c.get('customer_id')}: {e}")
            
    print(f"✓ Migrated {migrated_customers} / {len(customers)} customers.")
    
    # 4. Migrate Events
    migrated_events = 0
    for e in events:
        try:
            # We mark these as 'batch' source since they are from the historical detected_events.json
            insert_event(e, source="batch")
            migrated_events += 1
        except Exception as e:
            print(f"[Error] Failed to insert event for {e.get('customer_id')}: {e}")
            
    print(f"✓ Migrated {migrated_events} / {len(events)} events.")
    
    # 5. Migrate Agent Runs
    migrated_runs = 0
    migrated_steps = 0
    for r in runs:
        try:
            # db.insert_agent_run automatically finds/creates the matching event
            run_id = insert_agent_run(r)
            migrated_runs += 1
            migrated_steps += len(r.get("trace", []))
        except Exception as e:
            print(f"[Error] Failed to insert agent run for {r.get('customer_id')}: {e}")
            import traceback
            traceback.print_exc()
            
    print(f"✓ Migrated {migrated_runs} / {len(runs)} agent runs containing {migrated_steps} trace steps.")
    print("\nMigration completed successfully.")

if __name__ == "__main__":
    migrate()
