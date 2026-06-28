import os
"""
FinTwin — Backend API server
--------------------------------
Serves the agent run data to the frontend, manages the live feed simulator,
and handles WebSocket pushing of real-time agent output.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import refactored engine and simulator
from agent_engine import process_customer
from live_feed import TransactionSimulator
import db

DATA_DIR = Path("data")
RUNS_FILE = DATA_DIR / "agent_runs.json"

app = FastAPI(title="FinTwin Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global Live Feed & WebSocket State
# ---------------------------------------------------------------------------
live_feed_running = False
speed_multiplier = 1
simulator = None

# FIFO queue for rate-limit safe agent processing
agent_queue = None

# Thread-safe lock for agent_runs.json filesystem access
file_lock = None

# Set of (customer_id, event_type, month) representing processed events to avoid duplicate LLM calls
processed_events: Set[Tuple[str, str, int]] = set()

# Set to keep strong references to background tasks so they don't get GC'd
background_tasks: Set[asyncio.Task] = set()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WS] Client disconnected. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WS] Error broadcasting message: {e}")


manager = ConnectionManager()

# ---------------------------------------------------------------------------
# Background Task Loops
# ---------------------------------------------------------------------------

async def transaction_generator_loop():
    """Generates continuous transactions for random customers at the speed rate."""
    global live_feed_running, speed_multiplier, simulator
    print("[DEBUG] transaction_generator_loop function entered")
    
    # Track when we last injected an event to space them out at 1x speed
    import time
    last_event_injection_time = 0.0
    
    while True:
        try:
            print(f"[DEBUG] tick — generating transaction for a customer")
            print(f"[DEBUG] tick — live_feed_running={live_feed_running}, simulator_is_none={simulator is None}, speed={speed_multiplier}x")
            if live_feed_running and simulator is not None:
                current_time = time.time()
                import random
                
                # inject an event with a 10% chance per tick, spaced by at least 15 seconds real time
                should_inject_event = (random.random() < 0.40) and (current_time - last_event_injection_time > 5.0)
                
                cid = random_customer_id()
                print(f"[DEBUG] selected customer: cid={cid}, should_inject={should_inject_event}")
                if cid:
                    if should_inject_event:
                        etype = random.choice(["salary_jump", "new_emi", "savings_milestone"])
                        print(f"[Simulator] Injecting event '{etype}' for customer {cid}...")
                        txn = simulator.force_month_transition_with_event(cid, etype)
                        last_event_injection_time = current_time
                    else:
                        txn = simulator.generate_next_transaction(cid)
                    
                    print(f"[DEBUG] transaction generated: {txn.get('date')} | {txn.get('category')} | ₹{txn.get('amount')}")
                    
                    # Broadcast the transaction to WebSocket clients
                    await manager.broadcast({
                        "type": "transaction",
                        "id": f"{txn.get('date')}-{cid}-{txn.get('amount')}",
                        "customer_id": cid,
                        "customer_name": c_name(cid),
                        "amount": txn.get("amount"),
                        "category": txn.get("category"),
                        "date": txn.get("date"),
                        "is_life_event": should_inject_event
                    })
                    
                    # Check for new life events
                    detected = simulator.check_events_for_customer(cid)
                    for event in detected:
                        etype = event.get("event_type")
                        month = event.get("detected_month", 6)
                        event_key = (cid, etype, month)
                        
                        if event_key not in processed_events:
                            processed_events.add(event_key)
                            print(f"[Simulator] New event detected for {cid} ({c_name(cid)}): {event.get('event_label')}")
                            # Hand event to agent queue
                            await agent_queue.put((event, simulator.customers[cid]))
                
                # Base delay is 4 seconds, scaled by multiplier
                delay = max(0.05, 4.0 / speed_multiplier)
                await asyncio.sleep(delay)
            else:
                # Idle sleep if simulator is stopped
                await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[DEBUG] Error in transaction_generator_loop: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            await asyncio.sleep(1.0)


async def send_to_n8n(payload: dict) -> bool:
    """Helper to send an email payload to the n8n webhook."""
    import httpx
    N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/fintwin-engine")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            print(f"[n8n payload]: {json.dumps(payload, ensure_ascii=False)}")
            resp = await client.post(N8N_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[n8n] Send failed: {e}")
        return False


async def agent_worker_loop():
    """Dequeues detected events, processes them through the LLM agent, and broadcasts them."""
    print("[Agent Worker] Started agent queue processor background loop.")
    
    while True:
        try:
            # 1. Fetch next event from the queue
            event, customer = await agent_queue.get()
            cid = customer.get("customer_id")
            print(f"[Agent Worker] Processing event for {cid} ({customer.get('name')}) — Queue size: {agent_queue.qsize()}")
            
            # 2. Run LLM agent (investigate -> decide -> draft -> validate)
            # process_customer is synchronous, run in a separate thread so it doesn't block the event loop
            result = await asyncio.to_thread(process_customer, event, customer)
            
            # Ensure result dict has age and city from customer profile
            if "age" not in result or not result.get("age"):
                if simulator and cid in simulator.customers:
                    result["age"] = simulator.customers[cid].get("age", "")
                elif customer:
                    result["age"] = customer.get("age", "")
                else:
                    result["age"] = ""

            if "city" not in result or not result.get("city"):
                if simulator and cid in simulator.customers:
                    result["city"] = simulator.customers[cid].get("city", "")
                elif customer:
                    result["city"] = customer.get("city", "")
                else:
                    result["city"] = ""
            
            # 3. Save result to SQLite database
            await asyncio.to_thread(db.insert_agent_run, result)
            
            # 4. Push updates to WebSocket clients immediately
            await manager.broadcast(result)
            print(f"[Agent Worker] Successfully processed {cid}. Cooldown starts.")
            
            # 5. Auto-send: high priority + compliance clean = send without human intervention
            priority = (result.get("priority") or "").lower()
            was_revised = result.get("outreach", {}).get("was_revised", True)
            if priority == "high" and not was_revised:
                payload = {
                    "customer_name": result.get("customer_name"),
                    "age": result.get("age", ""),
                    "city": result.get("city", ""),
                    "event_type": result.get("event_label") or result.get("event_type"),
                    "signal": result.get("signal"),
                    "recommended_products": ", ".join(result.get("final_products", [])),
                    "email": "dev.1806raikwar21@gmail.com",
                    "to_email": "dev.1806raikwar21@gmail.com",
                    "phone": "+919876543210",
                    "priority": priority,
                    "email_body": result.get("outreach", {}).get("body", ""),
                    "subject": result.get("outreach", {}).get("subject", "") or f"SBI FinTwin — {result.get('event_label', 'Important Update')}",
                }
                success = await send_to_n8n(payload)
                if success:
                    print(f"[AutoSend] ⚡ Auto-sent email for {cid} ({result.get('customer_name')}) — high priority, compliance clean")
                    # Log to email_deliveries table
                    await asyncio.to_thread(
                        db.record_email_delivery,
                        result.get("run_id"),
                        "dev.1806raikwar21@gmail.com",
                        "auto_sent",
                        None
                    )
                    # Broadcast auto-send status so frontend can update the card
                    await manager.broadcast({
                        "type": "auto_sent",
                        "customer_id": cid,
                    })
            else:
                reason = "low/medium priority" if priority != "high" else "compliance revised"
                print(f"[Agent Worker] {cid} queued for manual review ({reason})")
            
            # 5. Rate limit safety delay (8 seconds) to protect free-tier API quotas
            await asyncio.sleep(8.0)
            agent_queue.task_done()
            
        except Exception as e:
            print(f"[Agent Worker] Error in worker: {e}", file=sys.stderr)
            await asyncio.sleep(2.0)  # Wait a bit on error before retrying


def random_customer_id() -> str:
    if simulator and simulator.customers:
        return random_choice(list(simulator.customers.keys()))
    return ""

def c_name(cid: str) -> str:
    if simulator and cid in simulator.customers:
        return simulator.customers[cid].get("name", "Unknown")
    return "Unknown"

# Stable helper to choose randomly since random.choice is standard
def random_choice(lst):
    import random
    return random.choice(lst) if lst else None

# ---------------------------------------------------------------------------
# Server Lifecycle Events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    global simulator, processed_events, agent_queue
    print("[Startup] Initializing database, transaction simulator and loading history...")
    db.init_db()
    agent_queue = asyncio.Queue()
    simulator = TransactionSimulator()
    
    # Pre-populate processed events from database
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT r.customer_id, e.event_type, e.detected_month
        FROM agent_runs r
        JOIN events e ON r.event_id = e.event_id
        """)
        rows = cursor.fetchall()
        for r in rows:
            cid = r["customer_id"]
            etype = r["event_type"]
            month = r["detected_month"] or 6
            if cid and etype:
                processed_events.add((cid, etype, month))
        print(f"[Startup] Loaded {len(processed_events)} previously processed events from database.")
    except Exception as e:
        print(f"[Startup] Error pre-populating processed events: {e}")
    finally:
        conn.close()
            
    # Launch background loops
    task_gen = asyncio.create_task(transaction_generator_loop())
    background_tasks.add(task_gen)
    task_gen.add_done_callback(background_tasks.discard)

    task_worker = asyncio.create_task(agent_worker_loop())
    background_tasks.add(task_worker)
    task_worker.add_done_callback(background_tasks.discard)

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/runs")
async def get_runs():
    try:
        return await asyncio.to_thread(db.get_all_runs)
    except Exception as e:
        print(f"Error fetching runs from database: {e}")
        return []


@app.get("/api/runs/{customer_id}")
async def get_run(customer_id: str):
    try:
        run = await asyncio.to_thread(db.get_run_by_customer, customer_id)
        if not run:
            raise HTTPException(404, f"No run found for {customer_id}")
        return run
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error querying database: {e}")



@app.post("/api/send-email")
async def send_email(payload: dict):
    """Manually send an outreach email via the n8n webhook."""
    # Build payload matching n8n requirements
    body_text = payload.get("email_body", payload.get("body", ""))
    prods = payload.get("recommended_products", "")
    customer_name = payload.get("customer_name", "Valued Customer")
    event_type = payload.get("event_type", "")
    signal = payload.get("signal", "")
    priority = payload.get("priority", "high")

    products_rows = ""
    for i, p in enumerate(prods.split(",")):
        p = p.strip()
        if p:
            row_bg = "#FAFBFE" if i % 2 else "#FFFFFF"
            products_rows += f'''<tr style="background:{row_bg}">
<td style="padding:12px 14px;border-bottom:1px solid #E0E0E0;font-size:13px;font-weight:500;color:#1A2233;width:40%">{p}</td>
<td style="padding:12px 14px;border-bottom:1px solid #E0E0E0;font-size:12px;color:#5B6B85;width:40%">Recommended based on your current financial profile and recent activity</td>
<td style="padding:12px 14px;border-bottom:1px solid #E0E0E0;width:20%;text-align:center"><a href="https://onlinesbi.sbi" style="background:#1B5FA8;color:#FFFFFF;padding:8px 14px;border-radius:4px;text-decoration:none;font-size:11px;font-weight:700;display:inline-block">Apply Now</a></td>
</tr>'''

    html_body = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:20px;background:#f0f2f5;font-family:Arial,sans-serif">
<div style="max-width:600px;margin:0 auto;background:#FFFFFF;border:1px solid #E0E0E0;border-radius:10px;overflow:hidden">

  <!-- Header -->
  <div style="background:#1B2A4A;padding:24px 28px">
    <div style="font-size:22px;color:#D4A24C;font-weight:normal">FinTwin by SBI</div>
    <div style="font-size:13px;color:#8C9AB5;margin-top:4px">Proactive Financial Intelligence</div>
  </div>

  <!-- Alert Banner -->
  <div style="background:#EAF1FB;padding:14px 28px;border-left:4px solid #1B5FA8">
    <div style="font-size:14px;font-weight:700;color:#1B5FA8">{event_type}</div>
    <div style="font-size:12px;color:#5B6B85;margin-top:3px">{signal}</div>
  </div>

  <!-- Greeting + Body -->
  <div style="padding:24px 28px;background:#FFFFFF">
    <div style="font-size:16px;color:#1A2233;margin-bottom:12px">Dear <strong>{customer_name}</strong>,</div>
    <div style="font-size:14px;color:#5B6B85;line-height:1.7;margin-bottom:24px">{body_text}</div>

    <!-- Products Table -->
    <div style="background:#F4F7FC;border-radius:8px;padding:18px;margin-bottom:20px">
      <div style="font-size:14px;font-weight:700;color:#1A2233;margin-bottom:12px">Recommended for You</div>
      <table style="width:100%;border-collapse:collapse">
        <tr style="background:#1B2A4A">
          <th style="padding:10px 14px;text-align:left;font-size:12px;font-weight:normal;color:#D4A24C;width:40%">Product</th>
          <th style="padding:10px 14px;text-align:left;font-size:12px;font-weight:normal;color:#D4A24C;width:40%">Why Now</th>
          <th style="padding:10px 14px;text-align:center;font-size:12px;font-weight:normal;color:#D4A24C;width:20%">Action</th>
        </tr>
        {products_rows}
      </table>
    </div>

    <!-- YONO CTA -->
    <div style="background:#1B2A4A;border-radius:8px;padding:20px;text-align:center;margin-bottom:16px">
      <div style="font-size:14px;color:#FFFFFF;margin-bottom:14px">Access all offers instantly on <strong style="color:#D4A24C">YONO SBI</strong></div>
      <a href="https://onlinesbi.sbi" style="background:#D4A24C;color:#1B2A4A;padding:12px 32px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:700;display:inline-block">Open YONO Now →</a>
    </div>

    <!-- Urgency -->
    <div style="background:#FFF3CD;border-left:3px solid #D4A24C;border-radius:6px;padding:14px 16px">
      <span style="font-size:12px;color:#856404"><strong>Act soon</strong> — these offers are personalised for your current financial profile and may change. Urgency: <strong>{priority}</strong></span>
    </div>
  </div>

  <!-- Footer -->
  <div style="background:#F4F7FC;padding:16px 28px;border-top:1px solid #E0E0E0">
    <p style="margin:0;font-size:11px;color:#8C9AB5;line-height:1.6">This message was generated by <strong>FinTwin</strong> — SBI's AI-powered proactive engagement system. You received this because a significant change was detected in your financial profile.</p>
    <p style="margin:8px 0 0;font-size:11px;color:#8C9AB5">State Bank of India | <a href="https://onlinesbi.sbi" style="color:#1B5FA8;text-decoration:none">onlinesbi.sbi</a> | <a href="#" style="color:#8C9AB5;text-decoration:none">Unsubscribe</a></p>
  </div>

</div>
</body>
</html>"""
    n8n_payload = {
        "customer_name": payload.get("customer_name"),
        "age": payload.get("age", ""),
        "city": payload.get("city", ""),
        "event_type": payload.get("event_type"),
        "signal": payload.get("signal"),
        "recommended_products": payload.get("recommended_products", ""),
        "email": payload.get("to_email", "dev.1806raikwar21@gmail.com"),
        "phone": "+919876543210",
        "subject": payload.get("subject", ""),
        "email_body": html_body,
    }
    
    success = await send_to_n8n(n8n_payload)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email to n8n webhook")
        
    # Log to email_deliveries table
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT r.run_id FROM agent_runs r
        JOIN customers c ON r.customer_id = c.customer_id
        WHERE c.name = ?
        ORDER BY r.created_at DESC LIMIT 1
        """, (payload.get("customer_name"),))
        row = cursor.fetchone()
        run_id = row["run_id"] if row else None
    except Exception as db_err:
        print(f"[API] Error resolving run_id: {db_err}")
        run_id = None
    finally:
        conn.close()

    await asyncio.to_thread(
        db.record_email_delivery,
        run_id,
        payload.get("to_email", "dev.1806raikwar21@gmail.com"),
        "sent",
        None
    )
    return {"success": True}


@app.post("/api/run-agent")
def trigger_agent():
    """Runs agent_engine.py as a subprocess (batch mode)."""
    try:
        result = subprocess.run(
            [sys.executable, "agent_engine.py"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-3000:],
            "stderr": result.stderr[-1500:] if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Agent run timed out after 5 minutes")


# --- Live Feed API controls ---

class SpeedControl(BaseModel):
    speed: int


@app.get("/api/feed/status")
async def get_feed_status():
    global live_feed_running, speed_multiplier
    return {
        "running": live_feed_running,
        "speed": speed_multiplier,
        "queue_size": agent_queue.qsize()
    }


@app.post("/api/feed/start")
async def start_feed():
    global live_feed_running
    live_feed_running = True
    print("[API] Live feed STARTED.")
    return await get_feed_status()


@app.post("/api/feed/stop")
async def stop_feed():
    global live_feed_running
    live_feed_running = False
    
    # Clear any pending backlog queue items as requested
    cleared_count = 0
    while not agent_queue.empty():
        try:
            agent_queue.get_nowait()
            agent_queue.task_done()
            cleared_count += 1
        except asyncio.QueueEmpty:
            break
            
    print(f"[API] Live feed STOPPED. Cleared {cleared_count} pending events from backlog.")
    return await get_feed_status()


@app.post("/api/feed/speed")
async def adjust_speed(control: SpeedControl):
    global speed_multiplier
    if control.speed not in [1, 5, 10, 20]:
         raise HTTPException(400, "Speed must be 1, 5, or 20")
    speed_multiplier = control.speed
    print(f"[API] Speed adjusted to {speed_multiplier}x.")
    return await get_feed_status()


# --- WebSocket endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Wait for any text (keeps connection alive and listens for client-initiated close)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Serve the frontend static files
# app.mount("/", StaticFiles(directory="static", html=True), name="static")  # disabled: frontend on Vercel


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
