#!/usr/bin/env python3
"""
FinTwin — Evaluation Harness
-----------------------------
Runs the agent against a hand-authored set of scenarios, validates output
across three core dimensions (Product-fit, Tool-usage, Compliance),
stores the results in SQLite, and prints a detailed report.
"""

import sys
import time
import argparse
from datetime import datetime
import db
from agent_engine import process_customer
from eval_scenarios import SCENARIOS

PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}

def evaluate_scenario(scenario: dict, run_data: dict) -> list[dict]:
    """
    Evaluates agent run output against the expected criteria for a scenario.
    Returns a list of dicts, one for each dimension, ready for insertion.
    """
    expected = scenario.get("expected", {})
    actual_products = run_data.get("final_products", [])
    actual_products_lower = [p.lower() for p in actual_products]
    actual_priority = run_data.get("priority", "medium")
    
    # Extract trace and find called tools
    called_tools = []
    for step in run_data.get("trace", []):
        if step.get("step") == "tool_call" and step.get("tool"):
            called_tools.append(step["tool"])
    called_tools_lower = [t.lower() for t in called_tools]
    
    was_revised = run_data.get("outreach", {}).get("was_revised", False)
    
    results = []
    
    # -------------------------------------------------------------------------
    # 1. Product-Fit Dimension
    # -------------------------------------------------------------------------
    product_fit_passed = True
    pf_reasons = []
    
    # Check avoided products
    for avoid in expected.get("avoid_products", []):
        if avoid.lower() in actual_products_lower:
            product_fit_passed = False
            pf_reasons.append(f"Recommended avoided product: '{avoid}'")
            
    # Check required products
    for req in expected.get("require_products", []):
        if req.lower() not in actual_products_lower:
            product_fit_passed = False
            pf_reasons.append(f"Missed required product: '{req}'")
            
    # Check max priority
    if "max_priority" in expected:
        max_p = expected["max_priority"]
        actual_rank = PRIORITY_RANK.get(actual_priority.lower(), 1)
        max_rank = PRIORITY_RANK.get(max_p.lower(), 2)
        if actual_rank > max_rank:
            product_fit_passed = False
            pf_reasons.append(f"Priority '{actual_priority}' exceeds max allowed '{max_p}'")
            
    # Check min priority
    if "min_priority" in expected:
        min_p = expected["min_priority"]
        actual_rank = PRIORITY_RANK.get(actual_priority.lower(), 1)
        min_rank = PRIORITY_RANK.get(min_p.lower(), 0)
        if actual_rank < min_rank:
            product_fit_passed = False
            pf_reasons.append(f"Priority '{actual_priority}' below min allowed '{min_p}'")
            
    pf_notes = "; ".join(pf_reasons) if pf_reasons else "Recommendation and priority are appropriate."
    results.append({
        "dimension": "product_fit",
        "passed": product_fit_passed,
        "actual_value": f"Products: {actual_products}, Priority: {actual_priority}",
        "expected_value": f"Avoid: {expected.get('avoid_products', [])}, Require: {expected.get('require_products', [])}, Max priority: {expected.get('max_priority', 'any')}",
        "notes": pf_notes
    })

    # -------------------------------------------------------------------------
    # 2. Tool-Usage Dimension
    # -------------------------------------------------------------------------
    tool_usage_passed = True
    tu_reasons = []
    
    # Check required tools
    for req_tool in expected.get("tools_required", []):
        if req_tool.lower() not in called_tools_lower:
            tool_usage_passed = False
            tu_reasons.append(f"Missed required tool: '{req_tool}'")
            
    # Check forbidden tools
    for forb_tool in expected.get("tools_forbidden", []):
        if forb_tool.lower() in called_tools_lower:
            tool_usage_passed = False
            tu_reasons.append(f"Called forbidden tool: '{forb_tool}'")
            
    tu_notes = "; ".join(tu_reasons) if tu_reasons else "Correct tools called during investigation."
    results.append({
        "dimension": "tool_usage",
        "passed": tool_usage_passed,
        "actual_value": f"Called tools: {called_tools}",
        "expected_value": f"Required tools: {expected.get('tools_required', [])}, Forbidden: {expected.get('tools_forbidden', [])}",
        "notes": tu_notes
    })

    # -------------------------------------------------------------------------
    # 3. Compliance Dimension
    # -------------------------------------------------------------------------
    compliance_passed = True
    comp_reasons = []
    
    if expected.get("expect_compliance_flag", False) and not was_revised:
        compliance_passed = False
        comp_reasons.append("Expected compliance revision flag, but message was not revised.")
        
    if expected.get("expect_no_compliance_flag", False) and was_revised:
        compliance_passed = False
        comp_reasons.append("Compliance flag triggered unexpectedly; message was revised.")
        
    comp_notes = "; ".join(comp_reasons) if comp_reasons else "Compliance check processed correctly."
    results.append({
        "dimension": "compliance",
        "passed": compliance_passed,
        "actual_value": f"was_revised: {was_revised}, Issues: {run_data.get('outreach', {}).get('issues', [])}",
        "expected_value": f"expect_compliance_flag: {expected.get('expect_compliance_flag', False)}, expect_no_compliance_flag: {expected.get('expect_no_compliance_flag', False)}",
        "notes": comp_notes
    })
    
    return results

def main():
    parser = argparse.ArgumentParser(description="FinTwin Agent Evaluation Framework")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of scenarios to run (default: run all)")
    args = parser.parse_args()
    
    db.init_db()  # Ensure database and tables exist
    
    scenarios_to_run = SCENARIOS
    if args.limit is not None:
        scenarios_to_run = SCENARIOS[:args.limit]
        
    run_timestamp = datetime.now().isoformat()
    
    print("=" * 70)
    print(f"STARTING EVALUATION RUN: {run_timestamp}")
    print(f"Scenarios Selected: {len(scenarios_to_run)} / {len(SCENARIOS)}")
    print("=" * 70)
    
    all_eval_rows = []
    consecutive_rate_limits = 0
    
    for i, s in enumerate(scenarios_to_run, 1):
        print(f"[{i}/{len(scenarios_to_run)}] Running scenario '{s['id']}': {s['name']}")
        
        # 1. Execute agent customer pipeline
        try:
            # Inject a safety cooldown between Groq API calls to avoid rate limits
            if i > 1:
                time.sleep(6)
                
            start_time = time.time()
            run_data = process_customer(s["event"], s["customer"])
            elapsed = time.time() - start_time
            print(f"  ✓ Agent finished in {elapsed:.1f}s")
            consecutive_rate_limits = 0  # Reset counter on success
            
            # Evaluate dimensions
            eval_results = evaluate_scenario(s, run_data)
            
            for res in eval_results:
                all_eval_rows.append({
                    "scenario_id": s["id"],
                    "scenario_name": s["name"],
                    "dimension": res["dimension"],
                    "passed": int(res["passed"]),
                    "actual_value": res["actual_value"],
                    "expected_value": res["expected_value"],
                    "notes": res["notes"],
                    "run_timestamp": run_timestamp
                })
                
                status_char = "✓" if res["passed"] else "✗"
                print(f"    {status_char} {res['dimension'].upper()}: {res['notes']}")
                
        except Exception as e:
            error_str = str(e)
            print(f"  ✗ Scenario run FAILED: {error_str}", file=sys.stderr)
            
            # Record failed evaluation rows for all 3 dimensions
            for dim in ["product_fit", "tool_usage", "compliance"]:
                all_eval_rows.append({
                    "scenario_id": s["id"],
                    "scenario_name": s["name"],
                    "dimension": dim,
                    "passed": 0,
                    "actual_value": "ERROR",
                    "expected_value": "AGENT RUN SUCCESS",
                    "notes": f"Agent failed to execute: {error_str}",
                    "run_timestamp": run_timestamp
                })
            
            if "rate limit" in error_str.lower() or "429" in error_str:
                consecutive_rate_limits += 1
                if consecutive_rate_limits >= 3:
                    print("\n[WARNING] Hit 3 consecutive API rate/quota limits. Stopping run early to conserve API usage.", file=sys.stderr)
                    break
                    
    # Write results to database
    if all_eval_rows:
        try:
            db.insert_eval_results(all_eval_rows)
            print(f"\n[Database] Wrote {len(all_eval_rows)} evaluation rows to SQLite table 'eval_results'.")
        except Exception as e:
            print(f"\n[Database] ERROR writing results to SQLite: {e}", file=sys.stderr)
            
    # Calculate and Print Summary Report
    print("\n" + "=" * 70)
    print("EVALUATION REPORT SUMMARY")
    print("=" * 70)
    
    by_dim = {"product_fit": {"passed": 0, "total": 0}, "tool_usage": {"passed": 0, "total": 0}, "compliance": {"passed": 0, "total": 0}}
    failures = []
    
    for row in all_eval_rows:
        dim = row["dimension"]
        by_dim[dim]["total"] += 1
        if row["passed"]:
            by_dim[dim]["passed"] += 1
        else:
            failures.append(row)
            
    total_passed = sum(d["passed"] for d in by_dim.values())
    total_items = sum(d["total"] for d in by_dim.values())
    
    for dim, stats in by_dim.items():
        pass_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] else 0.0
        print(f"Dimension {dim:<12}: {stats['passed']:>2} / {stats['total']:>2} passed ({pass_rate:.1f}%)")
        
    overall_pass_rate = (total_passed / total_items * 100) if total_items else 0.0
    print("-" * 70)
    print(f"OVERALL SCORE       : {total_passed:>2} / {total_items:>2} passed ({overall_pass_rate:.1f}%)")
    print("=" * 70)
    
    if failures:
        print("\nDETAILED FAILED SCENARIOS:")
        print("-" * 70)
        current_scenario = None
        for fail in failures:
            if current_scenario != fail["scenario_id"]:
                current_scenario = fail["scenario_id"]
                print(f"\n* Scenario '{fail['scenario_id']}': {fail['scenario_name']}")
            print(f"  - [{fail['dimension'].upper()}] failed:")
            print(f"    Expected: {fail['expected_value']}")
            print(f"    Actual  : {fail['actual_value']}")
            print(f"    Notes   : {fail['notes']}")
        print("-" * 70)
    else:
        print("\n✓ ALL TESTED SCENARIOS PASSED PERFECTLY!")
        print("=" * 70)

if __name__ == "__main__":
    main()
