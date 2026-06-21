"""
FinTwin — Day 2: Relationship Manager Dashboard
-------------------------------------------------
Run: streamlit run app.py

Reads data/recommendations.json (produced by agent.py) and presents it as
an RM-facing dashboard: a queue of customers with detected life events,
AI-generated reasoning for the product fit, and an editable outreach draft.
"""

import json
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="FinTwin — RM Dashboard",
    page_icon="🏦",
    layout="wide",
)

DATA_FILE = Path("data/recommendations.json")

PRIORITY_COLOR = {
    "high": "#d62728",
    "medium": "#ff9f1c",
    "low": "#2ca02c",
}


@st.cache_data
def load_recommendations():
    if not DATA_FILE.exists():
        return None
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def priority_badge(priority: str) -> str:
    color = PRIORITY_COLOR.get((priority or "").lower(), "#888888")
    label = (priority or "unknown").upper()
    return f"<span style='background:{color};color:white;padding:2px 10px;border-radius:10px;font-size:0.75rem;font-weight:600'>{label}</span>"


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

data = load_recommendations()

st.title("🏦 FinTwin — Relationship Manager Dashboard")
st.caption("AI-detected life events → personalized product reasoning → ready-to-send outreach")

if data is None:
    st.error(
        "No recommendations found. Run `python3 agent.py` first to generate "
        "`data/recommendations.json`."
    )
    st.stop()

if len(data) == 0:
    st.warning("recommendations.json is empty — no events were processed.")
    st.stop()

# Sort high -> medium -> low for the queue
priority_rank = {"high": 0, "medium": 1, "low": 2}
data_sorted = sorted(data, key=lambda r: priority_rank.get((r.get("priority") or "").lower(), 3))

# ---------------------------------------------------------------------------
# Layout: sidebar queue + main detail panel
# ---------------------------------------------------------------------------

col_queue, col_detail = st.columns([1, 2], gap="large")

with col_queue:
    st.subheader(f"Outreach Queue ({len(data_sorted)})")

    labels = []
    for r in data_sorted:
        p = (r.get("priority") or "unknown").upper()
        labels.append(f"[{p}] {r['customer_name']} — {r['event_label']}")

    selected_idx = st.radio(
        "Select a customer",
        options=range(len(data_sorted)),
        format_func=lambda i: labels[i],
        label_visibility="collapsed",
    )

selected = data_sorted[selected_idx]

with col_detail:
    header_col, badge_col = st.columns([3, 1])
    with header_col:
        st.subheader(f"{selected['customer_name']} · {selected['customer_id']}")
    with badge_col:
        st.markdown(priority_badge(selected.get("priority")), unsafe_allow_html=True)

    st.markdown(f"**Detected event:** {selected.get('event_label')}")
    st.markdown(f"**Signal:** {selected.get('signal')}")
    st.markdown(f"**Confidence:** {selected.get('confidence')}")
    if selected.get("priority_reason"):
        st.caption(f"Priority reason: {selected['priority_reason']}")

    st.divider()

    st.markdown("#### Recommended products")
    for p in selected.get("recommended_products", []):
        st.markdown(f"- **{p.get('name')}** _( {p.get('type')} )_")

    st.markdown("#### Why this fits")
    st.info(selected.get("ai_reasoning", "No reasoning generated."))

    st.divider()

    st.markdown("#### Outreach draft")
    outreach = selected.get("outreach") or {}
    channel = outreach.get("channel", "sms")
    st.caption(f"Channel: {channel.upper()}")

    if channel == "email" and outreach.get("subject"):
        st.text_input("Subject", value=outreach.get("subject", ""), key=f"subj_{selected['customer_id']}")

    edited_body = st.text_area(
        "Message body (editable before sending)",
        value=outreach.get("body", ""),
        height=150,
        key=f"body_{selected['customer_id']}",
    )

    b1, b2 = st.columns([1, 1])
    with b1:
        st.button("✅ Approve & Send", key=f"send_{selected['customer_id']}", type="primary")
    with b2:
        st.button("⏭️ Skip for now", key=f"skip_{selected['customer_id']}")

    st.caption("Demo mode — buttons are illustrative, no actual SMS/email is sent.")

st.divider()
st.caption(f"Showing {len(data_sorted)} AI-processed events · Powered by Gemini · FinTwin Day 2")
