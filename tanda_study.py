"""Simulation study: does the Tanda model actually work?

Everything here uses SIMULATED members whose true on-time probabilities we
know, so we can check the model against the truth.

  Study A  Interval coverage: do 90% credible intervals contain the true
           probability about 90% of the time?
  Study B  Decision value: how much expected loss does the recommended payout
           order save compared with a random order, a naive ranking, and the
           best possible order (which needs the true probabilities)?

Run:  python tanda_study.py            (about a minute)
      python tanda_study.py --quick    (a few seconds, rougher numbers)
"""
import argparse
import math
import random
import statistics as st

from tanda_loss import analyze_orders
from tanda_stats import (P_GRID, UNIFORM_PRIOR, credible_interval,
                         simulate_history, update)

N, C = 6, 100  # members, contribution per round


# ---------------------------------------------------------------- Study A
def coverage(true_p, n_months, trials, rng, level=0.90):
    """Fraction of simulated members whose interval contains their true p."""
    hits = 0
    for _ in range(trials):
        post = update(UNIFORM_PRIOR, simulate_history(true_p, n_months, rng))
        lo, hi = credible_interval(post, level)
        hits += lo <= true_p <= hi
    return hits / trials


def study_a(trials, rng):
    print("STUDY A: do the 90% intervals cover the true value?")
    print(f"({trials} simulated members per cell; the grid runs from 0.005 to 0.995)\n")
    months = [4, 8, 16, 32]
    print("true p  | " + " | ".join(f"{m:>2} months" for m in months))
    print("--------+-" + "-+-".join("---------" for _ in months))
    for p in [0.45, 0.60, 0.80, 0.90, 0.95, 0.98]:
        row = [coverage(p, m, trials, rng) for m in months]
        print(f"  {p:.2f}  | " + " | ".join(f"{c:>8.0%} " for c in row))
    # Average over true p values drawn from the grid itself (a Bayesian calibration check)
    print("\nAverage over true values drawn uniformly from the grid:")
    for m in months:
        hits = 0
        for _ in range(trials * 3):
            p = rng.choice(P_GRID)
            post = update(UNIFORM_PRIOR, simulate_history(p, m, rng))
            lo, hi = credible_interval(post)
            hits += lo <= p <= hi
        print(f"  {m:>2} months: {hits / (trials * 3):.0%}")


# ---------------------------------------------------------------- Study B
def true_expected_loss(order, true_p):
    """Exact expected loss of an order under the TRUE probabilities (rounds_done = 0)."""
    return C * sum((N - 1 - slot) * (1 - true_p[name]) for slot, name in enumerate(order))


def study_b(trials, rng):
    scenarios = {
        "4 months each":  lambda: [4] * N,
        "8 months each":  lambda: [8] * N,
        "16 months each": lambda: [16] * N,
        "mixed (2, 4, 8 or 16 months)": lambda: [rng.choice([2, 4, 8, 16]) for _ in range(N)],
    }
    names = [f"M{i + 1}" for i in range(N)]
    print("\nSTUDY B: expected loss of each strategy (average over simulated circles)")
    print(f"({trials} circles per scenario; true on-time probabilities drawn uniformly from 0.40 to 0.98)")
    print("Loss = expected dollars lost with $%d contributions. Lower is better.\n" % C)

    for label, length_fn in scenarios.items():
        rec, naive, rand_, oracle = [], [], [], []
        for _ in range(trials):
            true_p = {nm: rng.uniform(0.40, 0.98) for nm in names}
            lengths = length_fn()
            hist = {nm: simulate_history(true_p[nm], ln, rng) for nm, ln in zip(names, lengths)}

            best = analyze_orders(hist, C)["best"]["order"]            # the Tanda model
            raw = {nm: sum(h) / len(h) for nm, h in hist.items()}      # naive: raw fraction on time
            naive_order = sorted(names, key=lambda nm: (-raw[nm], rng.random()))
            oracle_order = sorted(names, key=lambda nm: -true_p[nm])   # needs the truth

            rec.append(true_expected_loss(best, true_p))
            naive.append(true_expected_loss(naive_order, true_p))
            oracle.append(true_expected_loss(oracle_order, true_p))
            # a random order's expected loss is exact: every member averages (N-1)/2 payments owed
            rand_.append(C * (N - 1) / 2 * sum(1 - p for p in true_p.values()))

        def se(xs):
            return st.stdev(xs) / math.sqrt(len(xs))
        gap = st.mean(rand_) - st.mean(oracle)
        print(label)
        print(f"  random order            ${st.mean(rand_):6.0f}")
        print(f"  naive (raw fraction)    ${st.mean(naive):6.0f}  (+/- {se(naive):.1f})")
        print(f"  Tanda (Bayesian)        ${st.mean(rec):6.0f}  (+/- {se(rec):.1f})")
        print(f"  best possible (oracle)  ${st.mean(oracle):6.0f}")
        print(f"  share of the random-to-best gap closed:  naive {(st.mean(rand_) - st.mean(naive)) / gap:.0%},"
              f"  Tanda {(st.mean(rand_) - st.mean(rec)) / gap:.0%}")
        # paired difference (same circles), so the comparison is fair
        diffs = [a - b for a, b in zip(naive, rec)]
        print(f"  Tanda vs naive, same circles: saves ${st.mean(diffs):.1f} on average "
              f"(+/- {se(diffs):.1f})\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    study_a(300 if args.quick else 2000, rng)
    study_b(40 if args.quick else 200, rng)