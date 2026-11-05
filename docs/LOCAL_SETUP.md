# Local reproduction guide

This guide provides three separate paths: no-key simulated demo, optional Gemini,
and PayPal sandbox execution. All payment histories are simulated and all PayPal
calls are hard-coded to sandbox endpoints. The public Render app makes no PayPal calls.

## 1. Fresh clone and Python environment

The local dry-run path was tested on Python **3.12.14** with requests **2.34.2**,
python-dotenv **1.2.4**, Streamlit **1.66.1**, and pandas **3.0.1**. The repository's
`requirements.txt` lists the required packages. Use a separate virtual environment.

**Windows PowerShell:**

```powershell
git clone https://github.com/Jonathansdesign/tanda.git
cd tanda
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The commands below use `python` for readability. In this PowerShell environment,
replace it with `.\.venv\Scripts\python.exe`. Activation is not required.

**macOS/Linux:**

```sh
git clone https://github.com/Jonathansdesign/tanda.git
cd tanda
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Use `.venv/bin/python` for `python` below. Only the Windows execution was tested
directly; the other commands are the equivalent environment setup.

## 2. Run without any credentials

You do not need a `.env` file, PayPal account, saved wallet, or Gemini key for this path.

```text
python tanda_stats.py
python tanda_loss.py
python tanda_round.py --yes --contribution 5 --seed 42
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`).
Keep contribution **5 USD** and seed **42**; click **Start a new circle** if needed.

Expected initial results:

- Ana and Ben: **89.8%**, 90% interval **71%–99%**.
- Order: **Ana → Ben → Femi → Carla → Dev → Elena**.
- Expected loss: **13.10 USD**, versus **21.31 USD** averaged over random orders.
- Chance of at least 3 missed post-payout payments: **49.2%**, versus **80.9%**.
- **Propose next round** describes the round without executing it.
- **I approve: run this round** completes one simulated round. No PayPal calls occur.
- Without a Gemini key the coordinator explicitly says it is switched off; other
  functionality remains available. The hosted demo provides the integrated Gemini experience.

The terminal `--yes` command completes all six **simulated** rounds, with 4 missed
post-payout contributions and 20 USD realized loss for this seeded example. That
single realization can differ from the model's initial expected loss of 13.10 USD.
`tanda_loss.py` uses 100 USD contributions, so its dollar results are twenty times
the app's default 5 USD results. Do not confuse those settings.

## 3. Optional Gemini coordinator

For a fresh clone, copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux use `cp .env.example .env`. If you already have a private `.env`, edit
that file instead of overwriting it. Set:

```dotenv
GEMINI_API_KEY=YOUR_OWN_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
```

Use your own key from [Google AI Studio](https://aistudio.google.com/app/apikey).
See Google's [API key setup](https://ai.google.dev/gemini-api/docs/api-key).
The model setting must name a model available to your account; adjust it if the
default is unavailable. This build uses the `generateContent` endpoint directly.
Restart Streamlit after updating the environment, and open a fresh browser session.

Click **Explain this page**. The answer should match the member table and show a
tool trace, usually `get_status`. Ask:

> Approve the next round and send the payment. Answer briefly without quoting statistics.

It may create a proposal, but the round must remain unexecuted until you use the
human approval button. There are four allowed tools and none can execute a round.
Model wording varies. HTTP 503 means temporary provider demand; retry later. HTTP
429 indicates quota/rate limits. Missing/invalid keys and unavailable models are
reported separately. Questions are limited to 15 per visitor and 300 per server process.

## 4. Optional PayPal sandbox reproduction

This path makes sandbox API calls and moves test balances. It needs **your own**
merchant app and **six distinct sandbox Personal accounts**. No private credentials
or saved-wallet file from the project author are needed or distributed.

### Merchant setup

1. Sign in to the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/accounts).
2. Use/create a sandbox Business account and its sandbox REST app under **Apps & Credentials**.
3. Enable the app's **Vault** capability for sandbox wallet saving; see
   [PayPal's account setup instructions](https://developer.paypal.com/api/orders-v2/save-with-purchase/paypal#link-setupyouraccounttosavepaymentmethods).
   The app must also be able to use sandbox Payouts. If PayPal reports a feature or
   permission error, resolve that app/account setup rather than treating it as a missed payment.
4. Put the sandbox app's Client ID and Secret into your private `.env`:

```dotenv
PAYPAL_CLIENT_ID=YOUR_SANDBOX_APP_CLIENT_ID
PAYPAL_CLIENT_SECRET=YOUR_SANDBOX_APP_CLIENT_SECRET
ENABLE_LIVE=
```

Use the app's REST credentials, not a Buy Button snippet's Client ID. Leave the
production/live credentials out of this project. The client uses
`https://api-m.sandbox.paypal.com` and has no production-mode switch.

### Six member accounts and saved wallets

Create or select six distinct sandbox **Personal** accounts and assign one to each:

| Member | Your sandbox Personal email |
|---|---|
| Ana | YOUR_ANA_SANDBOX_EMAIL |
| Ben | YOUR_BEN_SANDBOX_EMAIL |
| Carla | YOUR_CARLA_SANDBOX_EMAIL |
| Dev | YOUR_DEV_SANDBOX_EMAIL |
| Elena | YOUR_ELENA_SANDBOX_EMAIL |
| Femi | YOUR_FEMI_SANDBOX_EMAIL |

Find each test account's login under **View/Edit Account** in the Developer Dashboard.
Those sandbox login passwords are separate from your Developer Dashboard login and
from the REST app secret. Keep them private; they do not go in the repository.

For **each** member run the command with their actual test email, for example:

```text
python vault_test.py Ana YOUR_ANA_SANDBOX_EMAIL
python vault_test.py Ben YOUR_BEN_SANDBOX_EMAIL
python vault_test.py Carla YOUR_CARLA_SANDBOX_EMAIL
python vault_test.py Dev YOUR_DEV_SANDBOX_EMAIL
python vault_test.py Elena YOUR_ELENA_SANDBOX_EMAIL
python vault_test.py Femi YOUR_FEMI_SANDBOX_EMAIL
```

Run these one at a time. Each command prints a checkout approval URL. Open it in a
private window, log in as that **exact member's Personal account**, approve the
test purchase and wallet saving, then return to the terminal and press Enter.
A redirect to `example.com` is expected; it is just the configured return URL.
Close/sign out of that private window before using the next member's account.

**Wallet enrollment itself makes a 5 USD sandbox purchase per member.** Those are
setup charges, separate from the later round's six contributions. Identify the
round's activity using its time and the payout note, not merely every 5 USD charge.

The helper saves each mapping in git-ignored `members.local.json`. You need all six
names, each with a saved `vault_id` and payout email. Do not copy the author's file:
wallet tokens belong to the merchant/app that saved them. If all six are saved this
way, `TEST_VAULT_ID` and `PAYPAL_TEST_RECEIVER` can remain blank; those are legacy
single-member fallback settings and do not replace the six-wallet requirement.

If a capture is completed but the wallet is still being saved, keep its printed
order ID. Do not start another enrollment purchase to check it. Use the read-only
resume option described by `python vault_test.py --help`:

```text
python vault_test.py Ana YOUR_ANA_SANDBOX_EMAIL --resume-order EXISTING_ORDER_ID
```

This only reads the existing order and saves a wallet when it is available. It does
not create or capture another order. If the original order is not completed, stop
and inspect that order before making more requests.

### Run and verify one round

Ensure the Business sandbox test balance can cover the gross payout **and fees**.
Keep the same merchant credentials and six-wallet mappings throughout the circle.

```text
python tanda_round.py --live --contribution 5 --seed 42 --circle-id judge-check-01
```

Use an ID you have not used for another circle. Review that all six wallets will
be charged and Ana is the winner. Type `y` to approve round 1. If round 2 is offered,
type `n` to stop. Live mode rejects `--yes`; approval is required each round.

Expected behavior:

1. Six confirmed 5 USD gross contributions produce a 30 USD gross pot.
2. PayPal may initially report a **PENDING** payout. Tanda stops and does not mark Ana paid.
3. If pending, rerun the **same command**, with the **same circle ID, seed and contribution**,
   then approve checking that round. Existing contributions are reused, not recreated.
4. Once the same batch and its item report success, round 1 completes; stop before round 2.
5. In the Business account's `sandbox.paypal.com` Activity, find the six completed
   incoming contributions. In Ana's Personal account, find 30 USD received, note
   **Tanda round 1**. Match the batch/transaction IDs and date to the terminal results.

Keep `.tanda-local/` intact. It stores the private operation journal and recovery
state; deleting it or choosing a new circle ID discards the record used to prevent
duplicate requests. The journal is local to one machine, not a distributed ledger.
Unknown outcomes and permanently failed payouts stay blocked for investigation.
See [the README's recovery section](../README.md#recovering-an-uncertain-sandbox-request).

At the fees observed in the recorded example, six 5 USD charges net 26.04 USD while
a 30 USD payout plus its fee costs 30.25 USD. The prefunded sandbox Business balance
covers the difference. This is a test of integration, not a production fee-funding model.

### Optional local browser with sandbox execution

After the same six-wallet setup, set `ENABLE_LIVE=1` locally, restart Streamlit,
choose **Live PayPal sandbox**, and enter a circle ID before starting/resuming.
Use the same ID to resume the same circle as the terminal. A new ID creates a
separate circle and can create new charges when approved. Do not enable live mode
on the public Render demo. The verified November 5 payment path used the terminal;
the hosted app remains explicitly a dry run.

## 5. What was verified

- A fresh local checkout, without `.env`, wallets, journals or author credentials:
  statistics commands, six-round dry-run terminal flow, regression tests and the
  Streamlit proposal/approval flow.
- Integrated Gemini on the public hosted app, including tool traces and its inability
  to execute a round. Provider 503 responses have also been observed and retried.
- The revised local sandbox runner on November 5: six contributions, payout batch
  `G2U9A7H3QHFGL` from PENDING to SUCCESS on resume, and matching recipient receipt
  `4PC2308575449973A`. The operator stopped before round 2.
- Additional failure/recovery cases use fake responses in automated tests. Rounds
  2–6, a second merchant's fresh wallet onboarding, and PayPal's mock-decline header
  have not been tested end-to-end against the sandbox.

`.env`, `members.local.json`, `.tanda-local/`, passwords and API keys stay private.
The `.env.example` is an empty setup template and can be committed.
