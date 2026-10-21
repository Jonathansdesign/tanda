"""Tanda's web page. Run it with:  streamlit run app.py

HOW STREAMLIT WORKS (three ideas worth knowing)
1. Streamlit re-runs this whole file from top to bottom every time someone
   clicks something. So the file describes what the page should look like NOW.
2. Variables disappear on each re-run, so anything that must survive (the
   circle) lives in `st.session_state`, a dictionary that persists.
3. Buttons use "callbacks": a function Streamlit runs FIRST when the button is
   clicked, before it redraws the page. So the page always shows fresh state.

The statistics and PayPal code are not in this file. This page only asks
tanda_tools for results and displays them.
"""
import os

import pandas as pd
import streamlit as st

from tanda_tools import call_tool, new_demo_session
from tanda_view import (HOW_TO_READ, ledger_rows, md, order_text, proposal_lines,
                        risk_sentences, status_rows)

st.set_page_config(page_title="Tanda")

# Live PayPal calls are OFF unless the server sets ENABLE_LIVE=1 (in .env locally,
# or in Render's environment settings). This keeps a public demo from making calls.
LIVE_ALLOWED = os.getenv("ENABLE_LIVE") == "1"
LIVE_LABEL = "Live PayPal sandbox"


# ---------------------------------------------------------------- callbacks
def start_new_circle():
    """Build a fresh circle from the sidebar settings."""
    live = st.session_state["mode"] == LIVE_LABEL
    try:
        st.session_state["session"] = new_demo_session(
            live=live,
            contribution=float(st.session_state["contribution"]),
            seed=int(st.session_state["seed"]),
        )
        st.session_state["flash"] = None
    except Exception as e:                      # for example, missing PayPal keys
        st.session_state["flash"] = f"Could not start that circle: {e}"
    st.session_state["last_round"] = None


def do_propose():
    """AI-style step: describe the next round. Moves no money."""
    result = call_tool(st.session_state["session"], "propose_next_round")
    st.session_state["flash"] = result.get("error")
    st.session_state["last_round"] = None


def do_approve():
    """Human step: run the pending round. This is the only place money can move."""
    session = st.session_state["session"]
    if session.pending is None:
        st.session_state["flash"] = "There is no proposal to approve."
        return
    result = session.approve_and_run(session.pending["proposal_id"])
    st.session_state["flash"] = result.get("error")
    st.session_state["last_round"] = None if "error" in result else result


def do_cancel():
    st.session_state["session"].pending = None


# ------------------------------------------------------------------ sidebar
st.sidebar.header("Circle settings")
if LIVE_ALLOWED:
    st.sidebar.radio("Mode", ["Dry run", LIVE_LABEL], key="mode")
else:
    st.session_state["mode"] = "Dry run"
    st.sidebar.caption("Mode: dry run. Live PayPal calls are switched off on this server.")
st.sidebar.number_input("Contribution per member ($)", min_value=1.0, max_value=100.0,
                        value=5.0, step=1.0, key="contribution")
st.sidebar.number_input("Random seed", min_value=0, max_value=9999,
                        value=42, step=1, key="seed")
st.sidebar.button("Start a new circle", on_click=start_new_circle)
st.sidebar.caption("Settings apply when you start a new circle.")

if "session" not in st.session_state:
    start_new_circle()

# --------------------------------------------------------------------- page
st.title("Tanda")
st.caption("A savings-circle risk engine built on PayPal's sandbox. Members' payment "
           "histories are simulated and no real money moves.")

if st.session_state.get("flash"):
    st.error(st.session_state["flash"])
if "session" not in st.session_state:
    st.stop()                                   # nothing to show if startup failed

session = st.session_state["session"]
status = call_tool(session, "get_status")

if session.live:
    st.warning("Live sandbox mode: approving a round makes real PayPal sandbox calls "
               "(test money only).")
else:
    st.info("Dry run: nothing is sent to PayPal.")

# 1. Where the circle stands
if status["circle_complete"]:
    st.subheader("Circle complete")
    missed = sum(len(r["missed_by_paid_members"]) for r in session.ledger)
    st.success(md(f"All {status['total_rounds']} rounds are done. {missed} payment(s) were "
                  f"missed after payout (a loss of ${missed * session.contribution:.2f})."))
else:
    st.subheader(f"Round {status['round_to_run']} of {status['total_rounds']}")

table = pd.DataFrame(status_rows(status)).set_index("Member")
st.dataframe(table)
st.caption("Predicted chance each member pays on time")
st.bar_chart(table[["Predicted on-time"]])

if not status["circle_complete"]:
    # 2. The statistics' recommendation
    score = call_tool(session, "score_orders")
    st.subheader("Safest payout order")
    st.write(order_text(score["best_order"]))
    col1, col2 = st.columns(2)
    col1.metric("Expected loss (this order)", f"${score['expected_loss']:.2f}")
    col2.metric("Chance of a bad outcome", f"{score['chance_of_bad_outcome']:.1%}")
    for line in risk_sentences(score):
        st.write(md(line))

    # 3. Propose, then a human approves
    st.subheader("Next round")
    pending = session.pending
    if pending is None:
        st.button("Propose next round", on_click=do_propose)
        st.caption("A proposal only describes what would happen. It moves no money.")
    else:
        st.write(f"**Proposal {pending['proposal_id']}**")
        for line in proposal_lines(pending):
            st.write(md(line))
        st.warning("Nothing has happened yet. A person has to approve this.")
        b1, b2 = st.columns(2)
        b1.button("I approve: run this round", on_click=do_approve)
        b2.button("Cancel", on_click=do_cancel)

# 4. What just happened
last = st.session_state.get("last_round")
if last:
    st.success(md(f"Round {last['round']} finished: pot ${last['pot']:.2f}, "
                  f"winner {last['winner']}."))
    st.code("\n".join(last["details"] + [f"Payout: {last['payout']}"]))

if session.ledger:
    st.subheader("Rounds so far")
    st.dataframe(pd.DataFrame(ledger_rows(session.ledger)).set_index("Round"))

st.subheader("AI coordinator")
st.info("Not connected yet. When it is, a language model will explain this page in plain "
        "language using only the numbers above. It will be able to propose a round but "
        "never approve one.")

with st.expander("How to read these numbers"):
    st.markdown(HOW_TO_READ)