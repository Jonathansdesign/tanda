"""Tanda statistics: estimate each member's reliability from payment history.

Uses only: Bernoulli/binomial trials, Bayes' theorem, the law of total
probability, and a CDF. Everything is plain Python (no installs).
"""
import random
from math import comb

# Candidate values for a member's hidden on-time probability: 0.005, 0.010, ... 0.995.
# (199 values, 0.005 apart). More candidates means a closer match to the true,
# continuous answer; an earlier version used only 19 values and could not
# represent a member whose true rate is above 0.95.
GRID_STEPS = 200
P_GRID = [k / GRID_STEPS for k in range(1, GRID_STEPS)]
UNIFORM_PRIOR = [1 / len(P_GRID)] * len(P_GRID)


def simulate_history(true_p, n_months, rng):
    """Bernoulli trials: 1 = paid on time, 0 = late or missed."""
    return [1 if rng.random() < true_p else 0 for _ in range(n_months)]


def update(prior, history):
    """Bayes' theorem on the grid.

    Likelihood of k on-time payments out of n is the binomial PMF.
    The sum of prior * likelihood over the grid is P(data), by the
    law of total probability.
    """
    n = len(history)
    k = sum(history)
    unnormalized = [
        pr * comb(n, k) * p**k * (1 - p) ** (n - k)
        for p, pr in zip(P_GRID, prior)
    ]
    total = sum(unnormalized)
    return [u / total for u in unnormalized]


def predictive_on_time(posterior):
    """P(next payment on time) = sum over p of p * P(p | data)  (law of total probability)."""
    return sum(p * w for p, w in zip(P_GRID, posterior))


def credible_interval(posterior, level=0.90):
    """Read the interval off the posterior CDF."""
    lo_tail = (1 - level) / 2
    hi_tail = 1 - lo_tail
    cdf = 0.0
    lo = hi = None
    for p, w in zip(P_GRID, posterior):
        cdf += w
        if lo is None and cdf >= lo_tail:
            lo = p
        if cdf >= hi_tail:
            hi = p
            break
    return lo, (hi if hi is not None else P_GRID[-1])


def estimate_member(history, prior=None, level=0.90):
    """One call that gives everything the app (and later the AI agent) needs.

    Works on a payment history alone: no true_p required. This is the function
    the rest of Tanda should call for real members.
    """
    posterior = update(prior or UNIFORM_PRIOR, history)
    lo, hi = credible_interval(posterior, level)
    return {
        "n_months": len(history),
        "on_time": sum(history),
        "predicted_on_time": predictive_on_time(posterior),
        "interval": (lo, hi),
        "level": level,
    }


if __name__ == "__main__":
    # TEST MODE: true_p exists only so we can check the model against the truth.
    # Real members never have a known true_p.
    rng = random.Random(42)
    test_members = {"Ana": 0.95, "Ben": 0.90, "Carla": 0.80,
                    "Dev": 0.70, "Elena": 0.60, "Femi": 0.45}

    for name, true_p in test_members.items():
        history = simulate_history(true_p, 8, rng)
        est = estimate_member(history)
        lo, hi = est["interval"]
        print(f"{name:6} true={true_p:.2f}  history={history}  "
              f"predicted on-time={est['predicted_on_time']:.2f}  "
              f"90% interval=({lo:.2f}, {hi:.2f})")