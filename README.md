# Tanda

Savings circles run on trust and spreadsheets, so Tanda estimates each member's
reliability, recommends the payout order with the least expected loss, and moves
contributions and payouts through PayPal's sandbox. An AI coordinator (Google Gemini)
explains the circle in plain language and can propose the next round, but only a person
can approve it. (Prototype: tested on simulated circles.)

Built for the PayPal AI Hackathon (Oct 2026). Everything uses PayPal's **sandbox**:
no real money moves, and all member payment histories used for the statistics are
**simulated**.

## Live demo

**https://tanda-wma5.onrender.com/**

Hosted on Render's free plan, so the first visit after a quiet period can take about a
minute to wake up. The hosted page runs as a **dry run**: it makes no PayPal calls (see
Limitations). The PayPal sandbox flow is documented under "Results so far" below and
shown in the demo video.

To try it:

1. Read the member table and the "Safest payout order" box.
2. Click **Propose next round**, then **I approve: run this round**. Only that button
   runs a round.
3. Repeat, or ask the **AI coordinator** a question (for example "Who needs attention?").
   It explains the numbers and can propose a round, but it cannot approve one.

## The idea in plain English

In a rotating savings circle (a tanda, susu, or hui), 6 people each put in $100 a
month, and one person takes the whole $600 pot each month until everyone has had a
turn. Whoever is paid early has effectively borrowed from the others. If they stop
paying afterward, the rest lose money. So the payout order matters, and Tanda uses
probability to choose it.

## Who it is for and why it matters

**The practice.** Rotating savings circles are found in many communities. They go by
names such as [tandas and cundinas in Mexican communities and susus in the Caribbean](https://blog.massmutual.com/post/money-pools),
and researchers have profiled them among
[Nepali, Cambodian, Bangladeshi, Ethiopian, Eritrean, Kenyan, Mexican, Caribbean and Central American immigrants in the US](https://microfinancegateway.org/paper/2019/04/how-achieve-american-dream-immigrants-income).
They may appeal to people who
[cannot get the Social Security number banks ask for](https://blogs.und.edu/und-today/?p=32388).

**What already exists.** Software and programs for circles already exist, so Tanda is not
the first. San Francisco's Mission Asset Fund
[formalizes circles, collects the payments, and reports them to credit bureaus](https://www.philanthropy.com/news/formal-lending-circles-help-immigrants-build-credit-and-improve-their-lives/),
and a [consumer-finance article](https://www.experian.com/blogs/ask-experian/what-is-lending-circle)
names Esusu as another platform that does so. Their focus is building credit. Mission
Asset Fund has been [quoted reporting a 99% repayment rate](https://www.badcredit.org/news/maf-helps-underserved-financial-consumers-gain-access-and-build-credit/).
By contrast, informal circles run on trust with
[no contract or outside oversight](https://joingerald.com/learn/debt--credit/lending-circle-guide)
(a consumer-finance guide, so a weaker source).

**What Tanda adds.** A narrower question for a circle organizer: given each member's
payment history, which payout order carries the least risk, and how sure are we? Tanda
estimates each member's reliability with an honest uncertainty range, compares every
possible order, and explains the result in plain language. None of the sources I read
describe a tool that does this, though I cannot rule out that one exists.

**Honest limits of the impact case.**

- Where circles are formal and screened, reported default rates are very low, so Tanda's
  value is probably greatest for informal circles whose organizers cannot screen members.
- Everything here is a prototype tested on simulated circles and PayPal's sandbox. I have
  not tested it with real organizers or real payment histories.
- The statistical model rests on stated assumptions (see Model assumptions), and
  real members may not behave that way.

**What would come next.** Show the tool to circle organizers (with their consent) and
check whether the assumptions and the explanations match how circles really work, then
test it on real payment histories handled with their permission and privacy.

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
| AI coordinator (Gemini reads the circle through the tools and explains it) | `tanda_agent.py` | Built; answered a question with a real Gemini key |
| Web page (Streamlit): status, safest order, propose then human approves | `app.py`, `tanda_view.py` | Built; runs locally, dry-run flow verified |
| Hosted demo (Render, free plan, dry run) | | Deployed: https://tanda-wma5.onrender.com/ |
| Simulation study (validates the model against known truth) | `tanda_study.py` | Built and run |

## How it works

1. **Estimate** (`tanda_stats.py`). Each member has a hidden probability of paying
   on time. From their payment history (1 = on time, 0 = late or missed), Bayes'
   theorem updates a belief over a grid of 199 candidate values (0.5% to 99.5%).
   Output: a predicted on-time probability and a 90% credible interval.
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

## How PayPal is used

PayPal is the money layer: in a live circle, every contribution and every payout goes
through PayPal's sandbox. All calls go through one small client (`paypal_client.py`).

| What Tanda does | PayPal capability | Endpoint | Status |
|---|---|---|---|
| Authenticate | OAuth 2.0 client credentials | `POST /v1/oauth2/token` | Works; the token is reused until shortly before it expires |
| Save a member's wallet (they approve once) | Orders API with Vault (save during purchase) | `POST /v2/checkout/orders` with `payment_source.paypal.attributes.vault`, then `POST /v2/checkout/orders/{id}/capture` | Verified for all six members (vault status VAULTED) |
| Collect a contribution with nobody present | Charge a saved wallet through the Orders API | `POST /v2/checkout/orders` with `payment_source.paypal.vault_id` | Verified: charge completed, receipt reason "Billing Agreement" |
| Pay the round's winner | Payouts API | `POST /v1/payments/payouts`, `GET /v1/payments/payouts/{id}` | Verified: the recipient received the money |
| Simulate a declined charge | `PayPal-Mock-Response` test header (sandbox only) | on order creation | Written but **not tested** |

**Evidence from sandbox runs** (all sandbox test data, no real money):

- A saved wallet was charged $5.00: order `5VW6472472262700B`, completed. The
  recipient's receipt shows transaction `58N29882VB551984P`, reason "Billing Agreement",
  a $0.66 fee, and a net of $4.34.
- Live circle, round 1: all six members' saved wallets were charged $5.00 each, the
  pot was $30.00, and payout batch `NUS2T5FM5Q8G2` was sent to the winner, whose
  activity then showed transaction `27F14062VN813640C`, note "Tanda round 1", $30.00.
- An earlier test payout, batch `XDNCQQANB5P8G` ($5.00), also arrived in the recipient's account.

**Design choices around the money**

- A person approves every round before anything is charged or paid out.
- Orders carry a unique `PayPal-Request-Id`, and each payout batch has a unique
  `sender_batch_id`, so a retry cannot double-charge or double-pay.
- A PayPal error is turned into a plain message that includes PayPal's `debug_id`. In
  the circle, a refused charge from a member who was already paid becomes a 0 in
  that member's history.
- Everything runs in the sandbox, and the hosted demo makes no PayPal calls.

**Not done or not verified:** rounds 2 to 6 have not been run live, the declined-charge
test header is untested, and sandbox fees mean the money collected in a round is slightly
less than the sum of the contributions. Using saved wallets in production would likely
need extra PayPal approval, which I have not checked.

**Tools used:** PayPal REST APIs (Orders, Vault, Payouts) in the sandbox; Google
Gemini API for the coordinator; Render for hosting; Streamlit for the page; Python with
`requests`.

## Agent safety design

An AI model will coordinate the circle, but it cannot move money. `tanda_tools.py`
gives it four tools: look at the circle's status, estimate one member, score the
payout orders, and propose the next round. A proposal moves nothing. Running a round
is a separate function (`approve_and_run`) that a human triggers and that is not in
the list of tools the AI can call; a request for it by name is refused. All numbers
come from the Python statistics, not from the model, and the model is never shown
the simulated members' hidden true probabilities.

## AI tool used

Google's Gemini API (the `generateContent` endpoint, called with plain `requests`).
It acts as a coordinator: given a question, it asks for one or more of four safe tools
(circle status, one member's estimate, payout-order scoring, propose the next round),
reads the results our Python code produced, and explains them in plain language.
It does no math, never sees the simulated members' hidden true probabilities, cannot
approve a round, and cannot move money. The page shows which tools it used for each
answer, and a request for a tool outside the safe list is refused and shown as
"(refused)". Each visitor gets 15 questions and the server 300, to protect the free quota.

## Results so far (one simulated circle, seed 42)

Six simulated members, 8 months of history each. Model-estimated numbers:

| Order | Expected loss | Chance of 3+ missed payments |
|---|---|---|
| Best: Ana, Ben, Femi, Carla, Dev, Elena | $262 | 49.2% |
| Random order (average over all 720) | $426 | 80.9% |
| Worst | $590 | 95.6% |

This is a single run, scored with the model's own beliefs. A multi-run validation
against the true probabilities is planned (see Roadmap).

Playing that circle out with `tanda_round.py` (dry run, seed 42, $100 contributions),
the payout order held for all six rounds and 4 payments were missed after payout
(realized loss $400), versus the round-1 model estimate of $262. That is one random
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
| 0.45 | 95% | 92% | 92% | 92% |
| 0.60 | 98% | 94% | 88% | 90% |
| 0.80 | 97% | 95% | 89% | 93% |
| 0.90 | 95% | 97% | 94% | 87% |
| 0.95 | 81% | 94% | 96% | 93% |
| 0.98 | 93% | 84% | 95% | 87% |

Averaged over true values drawn from the grid: 90%, 90%, 91%, and 91% at 4, 8, 16
and 32 months, close to the 90% target. For a single fixed true value, coverage varies
from about 81% to 98% (the weakest cells: 0.95 with 4 months, 0.98 with 8 months, and
0.90 with 32 months), so intervals are approximately but not exactly calibrated.

**Study B: expected loss by strategy** (200 simulated circles per row; true
probabilities drawn uniformly from 0.40 to 0.98; $100 contributions; every order
is scored exactly using each member's true probability; lower is better)

| History per member | Random order | Naive (raw fraction) | Tanda (Bayesian) | Best possible |
|---|---|---|---|---|
| 4 months | $466 | $373 | $373 | $321 |
| 8 months | $463 | $356 | $359 | $319 |
| 16 months | $468 | $346 | $346 | $323 |
| Mixed (2, 4, 8 or 16) | $470 | $379 | $371 | $325 |

Findings:

- The recommended order closes about 64%, 72% and 84% of the gap between a random
  order and the best possible order at 4, 8 and 16 months. More history helps, with
  diminishing returns.
- With equal-length histories, the Bayesian ranking is no better than ranking by
  raw on-time fraction (differences of -$0.2, -$2.4 and -$0.3 per circle, each within
  about two standard errors, so consistent with no difference). This is expected: for
  equal lengths the posterior mean is an increasing function of the raw count.
- With unequal histories, Tanda saves $7.9 per circle (standard error 2.0, same
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
- **The probability grid is an approximation.** An earlier version used 19 candidate
  values (5% to 95%) and could not represent a member whose true rate is above 0.95:
  the study found 0% interval coverage for a 0.98 member. Refining the grid to 199
  values (0.5% to 99.5%) raised that to 84% to 95% and brought Ana's 8-for-8
  prediction to 0.90, matching the exact continuous answer (9/10) to within 0.002.
  Interval endpoints still move in steps of 0.005. An exact continuous (Beta)
  posterior is left for later.
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
- **The hosted demo is a dry run.** It shows the statistics, the approval flow, and the AI
  coordinator, but makes no PayPal calls, so a stranger cannot trigger sandbox payments
  from this account. The live PayPal runs (charges, payouts) are documented in this README
  and shown in the demo video. The free Render plan also goes to sleep when idle.
- **AI model names change.** Google renames and retires Gemini models often, so the
  model is a setting (`GEMINI_MODEL`) rather than a promise. On Google's free tier,
  questions and answers may be used to improve its products, which is acceptable here
  only because every member and payment history is simulated.
- **The AI is only as good as its tools.** It can explain the numbers but cannot check
  them, and a language model can still phrase things imprecisely, so the page shows the
  underlying table and the tools it used.
- **Live runs are lightly tested.** Round 1 of a live run is verified; the
  `--mock-decline` option (asking the sandbox to simulate a declined charge) is untested.
- **Real accounts always pay.** Each member has a real sandbox account with a saved
  wallet, but the sandbox always approves the charge, so real members never miss a
  payment on their own. Their payment histories (the track record the statistics
  use) are still simulated, and a missed payment can only be shown with simulated
  members or the untested `--mock-decline` option.

## Run it

1. Install a recent Python 3, then run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill in your sandbox credentials
   (Developer Dashboard, Apps & Credentials, Sandbox tab, Default Application):
   ```
   PAYPAL_CLIENT_ID=
   PAYPAL_CLIENT_SECRET=
   PAYPAL_TEST_RECEIVER=   # a sandbox Personal account email
   TEST_VAULT_ID=          # printed by vault_test.py
   ENABLE_LIVE=            # set to 1 to allow live PayPal calls from the web page
   GEMINI_API_KEY=         # free key from Google AI Studio (enables the AI coordinator)
   GEMINI_MODEL=           # optional; Google renames models often
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
6. Validation study: `python tanda_study.py` (under a minute on my machine;
   `--quick` for a rougher, faster version).
7. Web page: `pip install -r requirements.txt`, then
   `python -m streamlit run app.py`. It starts as a dry run (no PayPal calls).
   Click Propose next round, then approve it as the human.



# Roadmap

Done in this submission

 - Statistics: Bayesian reliability estimates and risk scoring of all payout orders
 - Validation study on simulated circles (interval coverage, loss versus baselines)
 - PayPal sandbox: saved wallets, charging them with nobody present, payouts
 - Round runner with a human approval step
 - Agent tool layer (read-only and propose-only tools) and a Gemini AI coordinator
 - Streamlit page, hosted on Render (dry run only)
 - Finer probability grid (199 values) to remove the 0.95 ceiling

Still to do before submitting

 - Demo video (the link goes at the top of this README once it is uploaded)

Future work (not part of submission)

- Exact continuous (Beta) posterior, once covered in class, to check the grid against the exact answer
- Sensitivity check: compare against a model where every payment updates beliefs
- Try the tool with real circle organizers (with their consent) and real payment histories

## Notes

- Built with help from AI for coding and explanations. I
  reviewed the code and can explain it.
- Created after the hackathon began (Oct 10, 2026). The early Buy Button test was
  setup practice, not part of the project.

## License

MIT