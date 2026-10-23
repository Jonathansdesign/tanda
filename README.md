# Tanda

Savings circles run on trust and spreadsheets, so Tanda estimates each member's
reliability, recommends the payout order with the least expected loss, and moves
contributions and payouts through PayPal's sandbox. (Work in progress. An AI agent
to coordinate the steps is planned and not built yet.)

Built for the PayPal AI Hackathon (Oct 2026). Everything uses PayPal's **sandbox**:
no real money moves, and all member payment histories used for the statistics are
**simulated**.


Live demo

https://tanda-wma5.onrender.com/

Hosted on Render's free plan, so the first visit after a quiet period can take about a minute to wake up. The hosted page runs as a dry run: it makes no PayPal calls (see Limitations). The PayPal sandbox flow is documented under "Results so far" below and shown in the demo video.

To try it:

Read the member table and the "Safest payout order" box.
Click Propose next round, then I approve: run this round. Only that button runs a round.
Repeat, or ask the AI coordinator a question (for example "Who needs attention?"). It explains the numbers and can propose a round, but it cannot approve one.

## The idea in plain English

In a rotating savings circle (a tanda, susu, or hui), 6 people each put in $100 a
month, and one person takes the whole $600 pot each month until everyone has had a
turn. Whoever is paid early has effectively borrowed from the others. If they stop
paying afterward, the rest lose money. So the payout order matters, and Tanda uses
probability to choose it.

## Status

| Piece | File(s) | Status |
|---|---|---|
| Estimate each member's on-time probability (Bayes) | `tanda_stats.py` | Built, runs on simulated data |
| Score all payout orders, pick the least risky | `tanda_loss.py` | Built, runs on simulated data |
| PayPal client (token reuse, errors, orders, payouts, vault) | `paypal_client.py` | Built, tested against the sandbox |
| Create a sandbox order | `create_order.py` | Works |
| Send a sandbox payout | `create_payout.py` | Works (payout arrives in the buyer account) |
| Save a member's PayPal wallet (approve once) | `vault_test.py`, `tanda_members.py` | Works; all six members have saved wallets |
| Charge a saved wallet with no one present | `vault_charge_test.py` | Works |
| Run a whole circle round by round, with human approval | `tanda_round.py` | Built. Dry run verified; live round 1 verified with six real sandbox members |
| Agent tool layer (what an AI is allowed to see and propose) | `tanda_tools.py` | Built and tested; works with any model |
| AI agent (an LLM that uses the tools and explains the plan) | | Not built, LLM not chosen yet |
| Web page (Streamlit): status, safest order, propose then human approves | `app.py`, `tanda_view.py` | Built; runs locally, dry-run flow verified |
| Hosted demo (Render) | | Not built |
| Simulation study (validates the model against known truth) | `tanda_study.py` | Built and run |

## How it works

1. **Estimate** (`tanda_stats.py`). Each member has a hidden probability of paying
   on time. From their payment history (1 = on time, 0 = late or missed), Bayes'
   theorem updates a belief over a grid of candidate values (5% to 95%). Output: a
   predicted on-time probability and a 90% credible interval.
2. **Score orders** (`tanda_loss.py`). For every possible payout order (720 for 6
   members), compute the distribution of total missed payments, then the expected
   dollar loss and the chance of a bad outcome (3 or more missed payments).
3. **Move money** (`paypal_client.py`). Contributions are charged to each member's
   saved PayPal wallet, and the round's pot is sent to the winner with the Payouts
   API. A refused charge raises an error that becomes a 0 in that member's history.
4. **Run the circle** (`tanda_round.py`). Each round: plan, ask a human to approve,
   collect contributions, record who missed, send the pot. Members without a saved
   wallet are simulated (clearly labeled in the output), so a demo can mix real
   sandbox members with simulated ones.

### Model assumptions

- N members each pay C per round. The member in slot s receives the pot in round s.
- A member who has **not yet** received the pot keeps paying. The risk is a member
  who already took the pot and then misses payments (they still owe N - s).
- Given a member's true on-time probability, missed payments are binomial. Members
  are independent. A late payment counts as a missed one.
- Without the second assumption every order would have the same total loss, and
  there would be nothing to optimize.
- Consequence: payments by members who have not been paid yet are treated as
  uninformative, so only post-payout payments update a member's history.

### Statistics used

Bernoulli and binomial trials, Bayes' theorem, the law of total probability, PMFs
and CDFs (tail probability), convolution of PMFs, exhaustive search over all N!
orders, and simulation (repeating a random experiment many times to check the
model: interval coverage, and paired comparisons with standard errors).

## Agent safety design

An AI model will coordinate the circle, but it cannot move money. `tanda_tools.py`
gives it four tools: look at the circle's status, estimate one member, score the
payout orders, and propose the next round. A proposal moves nothing. Running a round
is a separate function (`approve_and_run`) that a human triggers and that is not in
the list of tools the AI can call; a request for it by name is refused. All numbers
come from the Python statistics, not from the model, and the model is never shown
the simulated members' hidden true probabilities.

## Results so far (one simulated circle, seed 42)

Six simulated members, 8 months of history each. Model-estimated numbers:

| Order | Expected loss | Chance of 3+ missed payments |
|---|---|---|
| Best: Ana, Ben, Femi, Carla, Dev, Elena | $283 | 54.7% |
| Random order (average over all 720) | $438 | 82.6% |
| Worst | $593 | 95.7% |

This is a single run, scored with the model's own beliefs. A multi-run validation
against the true probabilities is planned (see Roadmap).

Playing that circle out with `tanda_round.py` (dry run, seed 42, $100 contributions),
the payout order held for all six rounds and 4 payments were missed after payout
(realized loss $400), versus the round-1 model estimate of $283. That is one random
circle, not a contradiction: the estimate is an average and single circles vary.
A member who missed payments after being paid (Femi) saw his estimate fall from
0.80 to 0.62 (his true simulated value is 0.45).

Live sandbox check (round 1): the circle ran with six saved sandbox wallets. All six
members were charged $5.00 through PayPal, the pot was $30.00, and a payout was sent
to the winner (batch status PENDING at the time). I stopped after round 1; rounds
2 to 6 have not been run live.

## Validation study (`python tanda_study.py`, seed 2026)

Simulated members whose true on-time probabilities are known, so the model can be
checked against the truth. The data are generated from the model's own assumptions
(independent payments, a fixed probability per member), so this shows how the
method behaves, not that real circles behave this way.

**Study A: do the 90% credible intervals cover the true value?** (2000 simulated
members per cell)

| True on-time probability | 4 months | 8 months | 16 months | 32 months |
|---|---|---|---|---|
| 0.45 | 95% | 97% | 92% | 94% |
| 0.60 | 98% | 94% | 96% | 96% |
| 0.80 | 97% | 95% | 97% | 95% |
| 0.90 | 95% | 97% | 94% | 96% |
| 0.95 | 81% | 94% | 96% | 98% |
| 0.98 | 0% | 0% | 0% | 0% |

Averaged over true values drawn from the grid: 93%, 95%, 95%, and 96% at 4, 8, 16
and 32 months. Intervals behave well except where the grid cannot reach the truth
(see Limitations).

**Study B: expected loss by strategy** (200 simulated circles per row; true
probabilities drawn uniformly from 0.40 to 0.98; $100 contributions; every order
is scored exactly using each member's true probability; lower is better)

| History per member | Random order | Naive (raw fraction) | Tanda (Bayesian) | Best possible |
|---|---|---|---|---|
| 4 months | $471 | $385 | $381 | $324 |
| 8 months | $457 | $349 | $347 | $311 |
| 16 months | $456 | $335 | $335 | $313 |
| Mixed (2, 4, 8 or 16) | $462 | $372 | $362 | $317 |

Findings:

- The recommended order closes about 61%, 75% and 85% of the gap between a random
  order and the best possible order at 4, 8 and 16 months. More history helps, with
  diminishing returns.
- With equal-length histories, the Bayesian ranking is no better than ranking by
  raw on-time fraction (a difference of $0.1 at 16 months, within noise). This is
  expected: for equal lengths the posterior mean is an increasing function of the
  raw count.
- With unequal histories, Tanda saves $9.6 per circle (standard error 2.3, same
  circles compared) over the naive ranking, because shrinkage stops a member with
  2 perfect payments from outranking one with 15 out of 16.
- The remaining value of the Bayesian approach is the uncertainty: credible
  intervals and the probability of a bad outcome, which a plain ranking cannot give.

## What went wrong along the way

- **Two different Client IDs.** The Buy Button's generated snippet has its own
  Client ID, separate from the Default Application's Client ID and Secret. The
  Python code uses the Default Application pair.
- **Sandbox vs. real accounts.** The "Business account" in the guides is a free
  sandbox test account that PayPal creates automatically, not a real one.
- **A seller can't pay itself.** Paying a test button while logged in as the
  sandbox Business account fails. Use a private window and a sandbox Personal account.
- **Payouts start as PENDING.** The client checks the status again afterward.
- **Vault orders label their link differently.** A normal order's approval link is
  `approve`, but a vault order's is `payer-action`, so the client handles both.
- **Fees.** The sandbox simulated a $0.66 fee on a $5.00 charge, so money collected
  in a round is slightly less than the sum of contributions.

## Limitations (honest)

- **Simulated data.** There is no real circle data. Histories are generated from
  known probabilities, so results show how the method behaves, not how real people behave.
- **Sandbox only.** Pooling and paying out real money is regulated, and saving
  payment methods for live use likely needs extra PayPal approval. Neither is covered here.
- **Small samples mislead.** With 8 months of history, a 45% payer who got lucky
  looks reliable (the model ranked "Femi" third). The 90% intervals show this uncertainty.
- **The 0.95 grid ceiling.** The probability grid stops at 0.95, so a member whose
  true on-time rate is 0.98 is never covered by their interval (0% in the study),
  and a 0.95 member with only 4 months of history is covered 81% of the time. A
  continuous (Beta) posterior would remove this. It is a planned refinement.
- **The order search confirmed a simple rule.** Across 200 simulated circles, the
  best order always matched "most reliable first." The added value is the risk
  numbers, not a surprising order.
- **The payout order never changes mid-circle.** Members already paid are fixed,
  and (by the model's own assumption) unpaid members' estimates never update, so
  re-planning each round cannot change who goes next. In 60 simulated circles the
  plan never changed. The per-round learning still updates risk estimates for
  members who have already been paid, which flags who needs follow-up, but it does
  not reorder anyone. Loosening the assumption (letting every payment update
  beliefs) is a planned sensitivity check.
- **Live runs are lightly tested.** Round 1 of a live run is verified; the
  `--mock-decline` option (asking the sandbox to simulate a declined charge) is untested.
- **Real accounts always pay.** Each member has a real sandbox account with a saved
  wallet, but the sandbox always approves the charge, so real members never miss a
  payment on their own. Their payment histories (the track record the statistics
  use) are still simulated, and a missed payment can only be shown with simulated
  members or the untested `--mock-decline` option.

## Run it

1. Install Python, then run `pip install requests python-dotenv`.
2. Copy `.env.example` to `.env` and fill in your sandbox credentials
   (Developer Dashboard, Apps & Credentials, Sandbox tab, Default Application):
   ```
   PAYPAL_CLIENT_ID=
   PAYPAL_CLIENT_SECRET=
   PAYPAL_TEST_RECEIVER=   # a sandbox Personal account email
   TEST_VAULT_ID=          # printed by vault_test.py
   ENABLE_LIVE=            # set to 1 to allow live PayPal calls from the web page
   ```
3. Statistics (no PayPal needed): `python tanda_stats.py` and `python tanda_loss.py`
4. PayPal sandbox: `python create_order.py`, `python create_payout.py`, then save
   each member's wallet once with `python vault_test.py NAME EMAIL` (approve in a
   private window while logged in as that exact sandbox Personal account). Wallets
   are saved to `members.local.json`, which is git-ignored. `python
   vault_charge_test.py` charges one saved wallet.
5. Whole circle: `python tanda_round.py` (dry run, no PayPal calls; add `--yes` to
   skip the approval prompts), then `python tanda_round.py --live` (real sandbox
   calls; the member Ana becomes real if `TEST_VAULT_ID` and `PAYPAL_TEST_RECEIVER`
   are set). Use a small `--contribution` for live runs.
6. Validation study: `python tanda_study.py` (about 15 seconds on my machine;
   `--quick` for a rougher, faster version).
7. Web page: `pip install -r requirements.txt`, then
   `python -m streamlit run app.py`. It starts as a dry run (no PayPal calls).
   Click Propose next round, then approve it as the human.

Never commit `.env`. It is listed in `.gitignore`.

## Roadmap

- [x] Round runner: charge saved wallets, record successes and failures, update
      the statistics, rescore the order, pay out the pot
- [x] Simulation study: loss versus random and best-possible orders over many
      circles, plus interval coverage
- [ ] Replace the grid with a continuous (Beta) posterior to remove the 0.95 ceiling
- [ ] Sensitivity check: compare against a model where every payment updates beliefs
- [x] Simple web app (Streamlit)
- [x] Agent tool layer: read-only tools plus propose-only, human-approved execution
- [ ] AI agent: an LLM that calls those tools, explains the plan, and drafts
      messages (choose a model and connect it)
- [ ] Deploy a hosted demo on Render
- [ ] Demo video and final write-up

## Notes

- Built with help from AI for coding and explanations. I reviewed the code and can explain it.
- Created after the hackathon began (Oct 10, 2026). The early Buy Button test was
  setup practice, not part of the project.

