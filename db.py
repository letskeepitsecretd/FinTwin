"""
FinTwin — SQLite Database Module
--------------------------------
Provides helper functions to initialize and query the SQLite database.
Schema description:
1. customers: customer_id (PK), name, age, city, base_salary, savings_balance, has_emi, existing_emi_amount, demo_email
2. events: event_id (PK), customer_id (FK), event_type, event_label, signal, confidence, detected_month, candidate_products, detected_at, source
3. agent_runs: run_id (PK), event_id (FK), customer_id (FK), reasoning, priority, priority_reason, final_products, outreach_channel, outreach_subject, outreach_body, was_revised, created_at
4. agent_trace_steps: step_id (PK), run_id (FK), step_type, step_order, tool_name, step_data, created_at
5. email_deliveries: delivery_id (PK), run_id (FK), to_email, status, error_message, sent_at
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path("/tmp/fintwin.db")

def init_db():
    """Initializes the SQLite database and creates the necessary tables."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Customers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        age INTEGER,
        city TEXT,
        base_salary INTEGER,
        savings_balance INTEGER,
        has_emi BOOLEAN,
        existing_emi_amount INTEGER,
        demo_email TEXT
    );
    """)

    # 2. Events Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_label TEXT NOT NULL,
        signal TEXT,
        confidence REAL,
        detected_month INTEGER,
        candidate_products TEXT, -- Store as JSON string: [{"name": "...", "type": "..."}]
        detected_at TEXT NOT NULL, -- ISO timestamp
        source TEXT NOT NULL, -- 'batch' or 'live'
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );
    """)

    # 3. Agent Runs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER,
        customer_id TEXT,
        reasoning TEXT,
        priority TEXT,
        priority_reason TEXT,
        final_products TEXT, -- Store as JSON string: ["product1", "product2"]
        outreach_channel TEXT,
        outreach_subject TEXT,
        outreach_body TEXT,
        was_revised BOOLEAN,
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(event_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );
    """)

    # 4. Agent Trace Steps Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_trace_steps (
        step_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        step_type TEXT NOT NULL,
        step_order INTEGER NOT NULL,
        tool_name TEXT,
        step_data TEXT, -- Store as JSON string
        created_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
    );
    """)

    # 5. Email Deliveries Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_deliveries (
        delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        to_email TEXT NOT NULL,
        status TEXT NOT NULL, -- 'sent', 'failed'
        error_message TEXT,
        sent_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
    );
    """)

    # 6. Evaluation Results Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eval_results (
        eval_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_id TEXT NOT NULL,
        scenario_name TEXT NOT NULL,
        dimension TEXT NOT NULL, -- 'product_fit', 'tool_usage', 'compliance'
        passed BOOLEAN NOT NULL,
        actual_value TEXT,
        expected_value TEXT,
        notes TEXT,
        run_timestamp TEXT NOT NULL
    );
    """)

    # Create indexes for foreign keys to optimize joins
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_customer ON events(customer_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_event ON agent_runs(event_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_customer ON agent_runs(customer_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trace_steps_run ON agent_trace_steps(run_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_deliveries_run ON email_deliveries(run_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eval_results_scenario ON eval_results(scenario_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eval_results_timestamp ON eval_results(run_timestamp);")

    conn.commit()
    conn.close()
    print("[Database] Initialized SQLite database successfully.")

def get_connection():
    """Returns a thread-safe connection to the SQLite database with WAL and Foreign Keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

# ---------------------------------------------------------------------------
# Insertion Helpers
# ---------------------------------------------------------------------------

def insert_customer(customer: dict):
    """Inserts or replaces a customer profile."""
    conn = get_connection()
    try:
        conn.execute("""
        INSERT OR REPLACE INTO customers (
            customer_id, name, age, city, base_salary, savings_balance, has_emi, existing_emi_amount, demo_email
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            customer.get("customer_id"),
            customer.get("name"),
            customer.get("age"),
            customer.get("city"),
            customer.get("base_salary"),
            customer.get("savings_balance"),
            customer.get("has_emi"),
            customer.get("existing_emi_amount"),
            customer.get("demo_email")
        ))
        conn.commit()
    finally:
        conn.close()

def insert_event(event: dict, source: str) -> int:
    """Inserts a detected event and returns its autogenerated event_id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        detected_at = event.get("detected_at")
        if not detected_at:
            detected_at = datetime.now().isoformat()
            
        cursor.execute("""
        INSERT INTO events (
            customer_id, event_type, event_label, signal, confidence, detected_month, candidate_products, detected_at, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.get("customer_id"),
            event.get("event_type"),
            event.get("event_label"),
            event.get("signal"),
            event.get("confidence"),
            event.get("detected_month"),
            json.dumps(event.get("recommended_products", [])),
            detected_at,
            source
        ))
        event_id = cursor.lastrowid
        conn.commit()
        return event_id
    finally:
        conn.close()

def insert_agent_run(run_data: dict) -> int:
    """Inserts a complete agent run and its trace steps in a transaction, returning run_id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Check if we need to resolve/create the event first
        # For new runs, we usually have an associated event_id or can find it.
        event_id = run_data.get("event_id")
        if not event_id:
            # Try to find the latest event for this customer + event_type
            cursor.execute("""
            SELECT event_id FROM events 
            WHERE customer_id = ? AND event_type = ? 
            ORDER BY detected_at DESC LIMIT 1
            """, (run_data.get("customer_id"), run_data.get("event_type")))
            row = cursor.fetchone()
            if row:
                event_id = row["event_id"]
            else:
                # Create a synthetic event from run data if none exists
                cursor.execute("""
                INSERT INTO events (
                    customer_id, event_type, event_label, signal, confidence, detected_month, candidate_products, detected_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_data.get("customer_id"),
                    run_data.get("event_type"),
                    run_data.get("event_label", "Unknown Event"),
                    run_data.get("signal"),
                    run_data.get("confidence"),
                    run_data.get("detected_month", 6),
                    json.dumps(run_data.get("candidate_products", [])),
                    datetime.now().isoformat(),
                    "batch"
                ))
                event_id = cursor.lastrowid
        
        # 2. Insert or replace the agent run row
        # (If same customer has a run, we update it in-place or insert a new one.
        # Original server.py logic updated run if customer_id matched. Let's do the same for SQLite)
        cursor.execute("SELECT run_id FROM agent_runs WHERE customer_id = ?", (run_data.get("customer_id"),))
        existing = cursor.fetchone()
        
        created_at = datetime.now().isoformat()
        outreach = run_data.get("outreach", {})
        
        if existing:
            run_id = existing["run_id"]
            # Delete old trace steps since we will write new ones
            cursor.execute("DELETE FROM agent_trace_steps WHERE run_id = ?", (run_id,))
            cursor.execute("""
            UPDATE agent_runs SET
                event_id = ?, reasoning = ?, priority = ?, priority_reason = ?, final_products = ?, 
                outreach_channel = ?, outreach_subject = ?, outreach_body = ?, was_revised = ?, created_at = ?
            WHERE run_id = ?
            """, (
                event_id,
                run_data.get("reasoning"),
                run_data.get("priority"),
                run_data.get("priority_reason"),
                json.dumps(run_data.get("final_products", [])),
                outreach.get("channel"),
                outreach.get("subject"),
                outreach.get("body"),
                outreach.get("was_revised", False),
                created_at,
                run_id
            ))
        else:
            cursor.execute("""
            INSERT INTO agent_runs (
                event_id, customer_id, reasoning, priority, priority_reason, final_products, 
                outreach_channel, outreach_subject, outreach_body, was_revised, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                run_data.get("customer_id"),
                run_data.get("reasoning"),
                run_data.get("priority"),
                run_data.get("priority_reason"),
                json.dumps(run_data.get("final_products", [])),
                outreach.get("channel"),
                outreach.get("subject"),
                outreach.get("body"),
                outreach.get("was_revised", False),
                created_at
            ))
            run_id = cursor.lastrowid

        # 3. Insert Trace Steps
        trace = run_data.get("trace", [])
        for order, step in enumerate(trace):
            cursor.execute("""
            INSERT INTO agent_trace_steps (
                run_id, step_type, step_order, tool_name, step_data, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                step.get("step"),
                order,
                step.get("tool"),
                json.dumps(step.get("result", {})),
                created_at
            ))
            
        conn.commit()
        return run_id
    finally:
        conn.close()

def record_email_delivery(run_id: int, to_email: str, status: str, error_message: str = None) -> int:
    """Logs an email delivery attempt to the email_deliveries audit table."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO email_deliveries (
            run_id, to_email, status, error_message, sent_at
        ) VALUES (?, ?, ?, ?, ?)
        """, (
            run_id,
            to_email,
            status,
            error_message,
            datetime.now().isoformat()
        ))
        delivery_id = cursor.lastrowid
        conn.commit()
        return delivery_id
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Query Helpers (Reconstructing the original JSON schema)
# ---------------------------------------------------------------------------

def _reconstruct_run(row, trace_rows) -> dict:
    """Helper to shape raw DB rows into the exact JSON format expected by the frontend."""
    # Reconstruct outreach dict
    outreach = {
        "channel": row["outreach_channel"],
        "subject": row["outreach_subject"] or "",
        "body": row["outreach_body"] or "",
        "was_revised": bool(row["was_revised"])
    }
    
    # Reconstruct trace list
    trace = []
    for step in trace_rows:
        trace_step = {
            "step": step["step_type"],
            "result": json.loads(step["step_data"])
        }
        if step["tool_name"]:
            trace_step["tool"] = step["tool_name"]
        trace.append(trace_step)
        
    return {
        "customer_id": row["customer_id"],
        "customer_name": row["customer_name"],
        "event_type": row["event_type"],
        "event_label": row["event_label"],
        "signal": row["signal"],
        "confidence": row["confidence"],
        "candidate_products": json.loads(row["candidate_products"] or "[]"),
        "final_products": json.loads(row["final_products"] or "[]"),
        "reasoning": row["reasoning"],
        "priority": row["priority"],
        "priority_reason": row["priority_reason"],
        "outreach": outreach,
        "trace": trace
    }

def get_all_runs() -> list:
    """Fetches all agent runs, joining relevant tables, and returns them in expected JSON format."""
    conn = get_connection()
    try:
        # Fetch all runs with event and customer details
        cursor = conn.cursor()
        cursor.execute("""
        SELECT 
            r.run_id, r.customer_id, r.reasoning, r.priority, r.priority_reason, r.final_products,
            r.outreach_channel, r.outreach_subject, r.outreach_body, r.was_revised,
            c.name AS customer_name,
            e.event_type, e.event_label, e.signal, e.confidence, e.candidate_products
        FROM agent_runs r
        LEFT JOIN customers c ON r.customer_id = c.customer_id
        LEFT JOIN events e ON r.event_id = e.event_id
        """)
        run_rows = cursor.fetchall()
        
        # Pre-fetch all trace steps to avoid N+1 queries
        cursor.execute("""
        SELECT run_id, step_type, tool_name, step_data 
        FROM agent_trace_steps 
        ORDER BY run_id, step_order
        """)
        trace_rows = cursor.fetchall()
        
        # Group trace steps by run_id
        traces_by_run = {}
        for step in trace_rows:
            traces_by_run.setdefault(step["run_id"], []).append(step)
            
        runs = []
        for row in run_rows:
            run_id = row["run_id"]
            runs.append(_reconstruct_run(row, traces_by_run.get(run_id, [])))
            
        return runs
    finally:
        conn.close()

def get_run_by_customer(customer_id: str) -> dict:
    """Fetches a single agent run by customer_id and returns it in expected JSON format (or None)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT 
            r.run_id, r.customer_id, r.reasoning, r.priority, r.priority_reason, r.final_products,
            r.outreach_channel, r.outreach_subject, r.outreach_body, r.was_revised,
            c.name AS customer_name,
            e.event_type, e.event_label, e.signal, e.confidence, e.candidate_products
        FROM agent_runs r
        LEFT JOIN customers c ON r.customer_id = c.customer_id
        LEFT JOIN events e ON r.event_id = e.event_id
        WHERE r.customer_id = ?
        """, (customer_id,))
        row = cursor.fetchone()
        if not row:
            return None
            
        run_id = row["run_id"]
        cursor.execute("""
        SELECT step_type, tool_name, step_data 
        FROM agent_trace_steps
        WHERE run_id = ?
        ORDER BY step_order
        """, (run_id,))
        trace_rows = cursor.fetchall()
        
        return _reconstruct_run(row, trace_rows)
    finally:
        conn.close()

def insert_eval_results(results: list[dict]):
    """Bulk inserts a list of evaluation results transactionally."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executemany("""
        INSERT INTO eval_results (
            scenario_id, scenario_name, dimension, passed, actual_value, expected_value, notes, run_timestamp
        ) VALUES (:scenario_id, :scenario_name, :dimension, :passed, :actual_value, :expected_value, :notes, :run_timestamp)
        """, results)
        conn.commit()
    finally:
        conn.close()

