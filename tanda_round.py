"""Run a whole Tanda circle, one round at a time.

Each round:
  1. PLAN     re-estimate every member and re-score the remaining payout orders
  2. APPROVE  a human says yes or no before any money moves
  3. COLLECT  charge each member's contribution (real PayPal wallet or simulated)
  4. LEARN    a member who already got the pot and missed a payment = a 0 in their history
  5. PAY OUT  send the pot to this round's winner

Run it safely first:   python tanda_round.py            (dry run: no PayPal calls)
Then for real:         python tanda_round.py --live     (sandbox PayPal calls)
"""
import argparse
import os
import random
from dataclasses import dataclass

from paypal_client import PayPalClient, PayPalError
from tanda_loss import analyze_orders
from tanda_stats import estimate_member, simulate_history


@dataclass
class Member:
    name: str
    history: list                 # track record: 1 = paid on time, 0 = missed
    true_p: float = 1.0           # SIMULATION ONLY: used when no PayPal wallet is attached
    email: str = None             # sandbox account that receives this member's payout
    vault_id: str = None          # saved PayPal wallet (makes this a "real" sandbox member)


def approve(message, auto):
    """Human-in-the-loop gate. Nothing moves until this returns True."""
    if auto:
        print(f"  [auto-approved] {message}")
        return True
    return input(f"  {message}  Approve? [y/N] ").strip().lower() == "y"


def collect(member, contribution, received, live, client, rng, mock_decline):
    """Collect one member's contribution. Returns (paid_ok, how)."""
    if live and member.vault_id:
        try:
            client.charge_vaulted(
                member.vault_id, contribution,
                reference=f"tanda-{member.name}",
                mock_error="INSTRUMENT_DECLINED" if (mock_decline and received) else None,
            )
            return True, "PayPal"
        except PayPalError as e:
            return False, f"PayPal refused ({e})"
    # Simulated member. Assumption from the model: someone who has NOT yet received
    # the pot keeps paying; someone who already did pays with probability true_p.
    p = member.true_p if received else 1.0
    return rng.random() < p, "simulated"


def plan_round(members, paid_out, rnd, contribution, bad_threshold=3):
    """Step 1 (PLAN): score the payout orders still possible this round.
    Members already paid are fixed; the rest are shuffled and compared."""
    return analyze_orders({m.name: m.history for m in members},
                          contribution, bad_threshold,
                          rounds_done=rnd, fixed_prefix=paid_out)


def execute_round(members, paid_out, rnd, contribution, winner, live, client, rng,
                  mock_decline=False, say=print):
    """Steps 3 to 5 for ONE round: collect, learn, pay out.

    This moves money (in live mode), so it must only run after a human approved.
    It changes `members` (histories) and `paid_out` in place and returns a record.
    `say` is where the progress lines go (print by default).
    """
    n = len(members)
    collected = 0.0
    missed_this_round = []
    for m in members:
        received = m.name in paid_out
        ok, how = collect(m, contribution, received, live, client, rng, mock_decline)
        say(f"  {m.name:6} {'paid  ' if ok else 'MISSED'}  ({how})")
        if ok:
            collected += contribution
        if received:                       # only post-payout behavior is informative
            m.history.append(1 if ok else 0)
            if not ok:
                missed_this_round.append(m.name)

    payout_note = "no PayPal account (simulated member)"
    if live and winner.email and collected > 0:
        try:
            res = client.send_payout(winner.email, collected, note=f"Tanda round {rnd + 1}")
            payout_note = f"sent, batch {res['payout_batch_id']} ({res['batch_status']})"
        except PayPalError as e:
            payout_note = f"FAILED ({e})"
    elif not live:
        payout_note = "dry run, nothing sent"
    say(f"Pot: ${collected:.2f} of ${contribution * n:.2f}. Payout to {winner.name}: {payout_note}")

    paid_out.append(winner.name)
    return {"round": rnd + 1, "winner": winner.name, "pot": collected,
            "missed_by_paid_members": missed_this_round, "payout": payout_note}


def run_circle(members, contribution=5.0, live=False, auto_approve=False,
               rng=None, client=None, bad_threshold=3, mock_decline=False):
    """Run every round in a loop, asking a human to approve each one."""
    rng = rng or random.Random()
    n = len(members)
    by_name = {m.name: m for m in members}
    paid_out = []                  # members already paid, in order
    ledger = []                    # one record per round
    realized_missed = 0            # missed payments by members who had already been paid
    first_plan = None

    for rnd in range(n):
        print(f"\n=== Round {rnd + 1} of {n} ===")
        plan = plan_round(members, paid_out, rnd, contribution, bad_threshold)
        best = plan["best"]
        first_plan = first_plan or plan
        winner = by_name[best["order"][rnd]]
        print("Plan: " + " -> ".join(best["order"]))
        print(f"      expected loss ${best['expected_loss']:.2f}, "
              f"chance of {bad_threshold}+ missed payments {best['p_bad']:.1%}")
        print(f"This round's winner: {winner.name}")

        n_real = sum(1 for m in members if m.vault_id) if live else 0
        what = (f"Charge {n_real} real sandbox wallet(s) ${contribution:.2f} each"
                if n_real else "Run this round (simulated, no PayPal calls)")
        if not approve(f"{what}, then pay the pot to {winner.name}.", auto_approve):
            print("Stopped: not approved. No further money moved.")
            break

        record = execute_round(members, paid_out, rnd, contribution, winner,
                               live, client, rng, mock_decline)
        realized_missed += len(record["missed_by_paid_members"])
        ledger.append(record)

    return {"ledger": ledger, "paid_out": paid_out, "realized_missed": realized_missed,
            "realized_loss": realized_missed * contribution, "first_plan": first_plan}


def demo_members(seed):
    """Six simulated members. If TEST_VAULT_ID and PAYPAL_TEST_RECEIVER are set in
    .env, Ana becomes a REAL sandbox member (saved wallet plus payout account)."""
    rng = random.Random(seed)
    true_p = {"Ana": 0.95, "Ben": 0.90, "Carla": 0.80,
              "Dev": 0.70, "Elena": 0.60, "Femi": 0.45}
    members = [Member(nm, simulate_history(p, 8, rng), true_p=p) for nm, p in true_p.items()]
    vault, email = os.getenv("TEST_VAULT_ID"), os.getenv("PAYPAL_TEST_RECEIVER")
    if vault and email:
        members[0].vault_id, members[0].email = vault, email
    return members


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run a Tanda circle.")
    ap.add_argument("--live", action="store_true", help="make real PayPal sandbox calls")
    ap.add_argument("--yes", action="store_true", help="auto-approve every round")
    ap.add_argument("--contribution", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mock-decline", action="store_true",
                    help="ask PayPal to simulate a declined charge for the real member after payout")
    args = ap.parse_args()

    members = demo_members(args.seed)
    client = PayPalClient() if args.live else None
    mode = "LIVE sandbox" if args.live else "DRY RUN"
    print(f"Tanda circle ({mode}), contribution ${args.contribution:.2f}, seed {args.seed}")

    result = run_circle(members, args.contribution, live=args.live, auto_approve=args.yes,
                        rng=random.Random(args.seed + 1), client=client,
                        mock_decline=args.mock_decline)

    print("\n=== Summary ===")
    print("Payout order actually used: " + " -> ".join(result["paid_out"]))
    print(f"Missed payments after payout: {result['realized_missed']} "
          f"(realized loss ${result['realized_loss']:.2f})")
    if result["first_plan"]:
        print(f"Round-1 model estimate of expected loss: ${result['first_plan']['best']['expected_loss']:.2f}")
    print("\nFinal reliability estimates (simulated members' true values in brackets):")
    for m in members:
        est = estimate_member(m.history)
        lo, hi = est["interval"]
        tag = "REAL sandbox member" if (args.live and m.vault_id) else f"true {m.true_p:.2f}"
        print(f"  {m.name:6} predicted {est['predicted_on_time']:.2f}  "
              f"90% ({lo:.2f}-{hi:.2f})  [{tag}]")