"""The tool layer for Tanda's AI agent.

WHAT THIS FILE IS
An AI model can only read and write text. To "act", it asks us to run a
function (a "tool") and then reads what the function returns. This file defines
those functions. It does not call any particular AI company, so it works with
whichever model you choose later.

THE SAFETY RULE (the main design idea)
The AI may only LOOK at the circle and PROPOSE a round. It can never move money.
Moving money is done by `approve_and_run`, which a HUMAN triggers (a button or a
typed "y") and which is deliberately NOT in the list of tools the AI can use.

THE STATISTICS STAY IN PYTHON
Every number comes from tanda_stats.py and tanda_loss.py. The AI explains and
suggests; it never does the math. It is also never shown `true_p`, the hidden
simulation truth, because a real circle would not know it either.
"""
import random

from tanda_round import Member, demo_members, execute_round, plan_round
from tanda_stats import estimate_member as _estimate

# A paid-out member whose predicted on-time probability falls below this gets
# flagged. 0.75 is an arbitrary cutoff chosen for the demo, not a statistical result.
WATCH_THRESHOLD = 0.75


class TandaSession:
    """Holds one circle's state: the members, who has been paid, and the current round."""

    def __init__(self, members, contribution=5.0, live=False, client=None,
                 rng=None, bad_threshold=3, mock_decline=False):
        self.members = members
        self.contribution = contribution
        self.live = live
        self.client = client
        self.rng = rng or random.Random()
        self.bad_threshold = bad_threshold
        self.mock_decline = mock_decline
        self.paid_out = []        # names already paid, in order
        self.rnd = 0              # index of the round about to run (0 = first)
        self.ledger = []          # one record per finished round
        self.pending = None       # the proposal waiting for a human, if any
        self._proposal_count = 0

    # ------------------------------------------------------------------
    # Helpers (not tools)
    # ------------------------------------------------------------------
    def _find(self, name):
        for m in self.members:
            if m.name.lower() == str(name).lower():
                return m
        return None

    @property
    def complete(self):
        return self.rnd >= len(self.members)

    # ------------------------------------------------------------------
    # TOOLS THE AI MAY USE (read-only, or propose-only). No money moves here.
    # ------------------------------------------------------------------
    def get_status(self):
        """Where the circle stands, with one summary line per member."""
        rows = []
        for m in self.members:
            est = _estimate(m.history)
            already_paid = m.name in self.paid_out
            predicted = est["predicted_on_time"]
            lo, hi = est["interval"]
            rows.append({
                "name": m.name,
                "already_paid": already_paid,
                "months_of_history": len(m.history),
                "predicted_on_time": round(predicted, 3),
                "interval_90": [round(lo, 2), round(hi, 2)],
                "needs_attention": bool(already_paid and predicted < WATCH_THRESHOLD),
                "has_paypal_wallet": bool(m.vault_id),
            })
        return {
            "round_to_run": min(self.rnd + 1, len(self.members)),
            "total_rounds": len(self.members),
            "circle_complete": self.complete,
            "contribution_each": self.contribution,
            "mode": "live PayPal sandbox" if self.live else "dry run (no PayPal calls)",
            "paid_out_in_order": list(self.paid_out),
            "watch_threshold": WATCH_THRESHOLD,
            "members": rows,
        }

    def estimate_member(self, name):
        """Reliability estimate for one member (probability of paying on time)."""
        m = self._find(name)
        if m is None:
            return {"error": f"unknown member '{name}'",
                    "known_members": [x.name for x in self.members]}
        est = _estimate(m.history)
        lo, hi = est["interval"]
        return {
            "name": m.name,
            "months_of_history": est["n_months"],
            "on_time_payments": est["on_time"],
            "predicted_on_time": round(est["predicted_on_time"], 3),
            "interval_90": [round(lo, 2), round(hi, 2)],
            "already_paid": m.name in self.paid_out,
        }

    def score_orders(self):
        """The best payout order still possible, with its risk and a random-order baseline."""
        if self.complete:
            return {"error": "the circle is complete; there is nothing left to plan"}
        plan = plan_round(self.members, self.paid_out, self.rnd,
                          self.contribution, self.bad_threshold)
        best, base = plan["best"], plan["random_baseline"]
        return {
            "best_order": list(best["order"]),
            "expected_loss": round(best["expected_loss"], 2),
            "chance_of_bad_outcome": round(best["p_bad"], 3),
            "bad_outcome_means": f"{self.bad_threshold} or more missed payments after being paid",
            "random_order_expected_loss": round(base["expected_loss"], 2),
            "random_order_chance_of_bad_outcome": round(base["p_bad"], 3),
            "orders_compared": plan["n_orders"],
        }

    def propose_next_round(self):
        """Prepare the next round for a HUMAN to approve. Moves no money."""
        if self.complete:
            return {"error": "the circle is complete; no more rounds to propose"}
        plan = plan_round(self.members, self.paid_out, self.rnd,
                          self.contribution, self.bad_threshold)
        best = plan["best"]
        winner = best["order"][self.rnd]
        real = [m.name for m in self.members if m.vault_id] if self.live else []
        self._proposal_count += 1
        self.pending = {
            "proposal_id": f"R{self.rnd + 1}-{self._proposal_count}",
            "round": self.rnd + 1,
            "winner": winner,
            "payout_order": list(best["order"]),
            "will_charge_real_paypal_wallets": real,
            "simulated_members": [m.name for m in self.members if m.name not in real],
            "contribution_each": self.contribution,
            "maximum_pot": round(self.contribution * len(self.members), 2),
            "expected_loss": round(best["expected_loss"], 2),
            "chance_of_bad_outcome": round(best["p_bad"], 3),
            "requires_human_approval": True,
            "money_moved": False,
        }
        return dict(self.pending)

    # ------------------------------------------------------------------
    # HUMANS ONLY. Deliberately not in AI_TOOLS below.
    # ------------------------------------------------------------------
    def approve_and_run(self, proposal_id):
        """Run the pending round. Call this only after a person said yes."""
        if self.pending is None:
            return {"error": "there is no pending proposal to approve"}
        if proposal_id != self.pending["proposal_id"]:
            return {"error": f"proposal '{proposal_id}' is not the pending one "
                             f"('{self.pending['proposal_id']}')"}
        lines = []
        winner = self._find(self.pending["winner"])
        record = execute_round(self.members, self.paid_out, self.rnd, self.contribution,
                               winner, self.live, self.client, self.rng,
                               self.mock_decline, say=lines.append)
        record["details"] = lines
        self.ledger.append(record)
        self.rnd += 1
        self.pending = None
        return record


def new_demo_session(live=False, contribution=5.0, seed=42):
    """Start a fresh demo circle (six simulated members; Ana is real if configured).

    live=False: a dry run, no PayPal calls. live=True: real sandbox calls.
    """
    members = demo_members(seed)
    client = None
    if live:
        from paypal_client import PayPalClient   # only needed (and only loaded) in live mode
        client = PayPalClient()
    return TandaSession(members, contribution=contribution, live=live, client=client,
                        rng=random.Random(seed + 1))


# ----------------------------------------------------------------------
# What the AI is allowed to call. Anything not in this table is refused.
# ----------------------------------------------------------------------
AI_TOOL_NAMES = ["get_status", "estimate_member", "score_orders", "propose_next_round"]

TOOL_SPECS = [
    {"name": "get_status",
     "description": "Get the circle's current state: which round is next, who has been paid, "
                    "and each member's predicted on-time probability with a 90% interval. "
                    "needs_attention=true means a member was already paid and their predicted "
                    "on-time probability is below the watch threshold (this does not by itself "
                    "say the estimate has fallen).",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "estimate_member",
     "description": "Get one member's estimated probability of paying on time, with a 90% "
                    "credible interval and their payment record.",
     "parameters": {"type": "object",
                    "properties": {"name": {"type": "string", "description": "Member's name"}},
                    "required": ["name"]}},
    {"name": "score_orders",
     "description": "Find the lowest-risk payout order still possible, with its expected dollar "
                    "loss and chance of a bad outcome, compared with a random order.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "propose_next_round",
     "description": "Prepare the next round (winner, who is charged, pot size) for a human to "
                    "approve. This moves NO money; a person must approve it separately.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
]

AGENT_INSTRUCTIONS = """You are the coordinator for a small savings circle (a tanda), \
built for a PayPal sandbox hackathon demo.

Rules:
1. Every number you state must come from a tool result. Never estimate or invent numbers.
2. You cannot move money. You can only look at the circle and propose the next round. \
A human approves every payment.
3. Explain results in plain language and always mention uncertainty (the intervals).
4. Say clearly that member payment histories are simulated and PayPal is the sandbox.
5. If a member already paid out has needs_attention=true, point it out and suggest a \
gentle next step for the organizer (such as a friendly reminder). You may draft the \
message text, but you cannot send it.
6. Keep answers short and end with what the human needs to decide."""


def call_tool(session, name, arguments=None):
    """Run a tool the AI asked for. Refuses anything not on the allowed list."""
    allowed = {
        "get_status": session.get_status,
        "estimate_member": session.estimate_member,
        "score_orders": session.score_orders,
        "propose_next_round": session.propose_next_round,
    }
    if name not in allowed:
        return {"error": f"'{name}' is not a tool you can use. "
                         f"Available tools: {AI_TOOL_NAMES}"}
    try:
        return allowed[name](**(arguments or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}


if __name__ == "__main__":
    # Quick look at what the AI would see (dry run, no PayPal, no AI model needed).
    import json
    s = TandaSession(demo_members(42), contribution=5.0, rng=random.Random(43))
    for tool in AI_TOOL_NAMES:
        args = {"name": "Femi"} if tool == "estimate_member" else {}
        print(f"--- {tool} ---")
        print(json.dumps(call_tool(s, tool, args), indent=2))