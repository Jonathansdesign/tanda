"""Small PayPal sandbox client used by Tanda.

Every PayPal call in the project goes through this one class, so the
rest of the code never repeats token or error handling.
"""
import json
import os
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api-m.sandbox.paypal.com"  # sandbox only: no real money


class PayPalError(Exception):
    """Raised when PayPal returns an error. Includes the debug_id PayPal asks for in support tickets."""

    def __init__(self, message, *, declined=False, rejected=False):
        super().__init__(message)
        self.declined = declined
        self.rejected = rejected


class PayPalClient:
    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id or os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("PAYPAL_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise PayPalError("Missing PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET in .env")
        self._token = None
        self._expires_at = 0.0

    # ---- authentication (token is reused until shortly before it expires) ----
    def _get_token(self):
        if self._token and time.time() < self._expires_at:
            return self._token
        try:
            resp = requests.post(
                f"{BASE}/v1/oauth2/token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise PayPalError("Could not authenticate with PayPal. No payment request was sent.",
                              rejected=True) from exc
        try:
            self._raise_if_error(resp)
        except PayPalError as exc:
            raise PayPalError(str(exc), rejected=True) from exc
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3000)) - 60
        return self._token

    # ---- shared request + error handling ----
    @staticmethod
    def _raise_if_error(resp):
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = {"message": resp.text}
            codes = {d.get("issue") for d in body.get("details", [])}
            declined = resp.status_code in (400, 422) and bool(
                codes & {"INSTRUMENT_DECLINED", "PAYER_CANNOT_PAY", "INSUFFICIENT_FUNDS"})
            raise PayPalError(
                f"HTTP {resp.status_code} {body.get('name', body.get('error', ''))}: "
                f"{body.get('message', body.get('error_description', ''))} "
                f"(debug_id={body.get('debug_id')})",
                declined=declined,
                rejected=resp.status_code in (400, 401, 403, 404, 422),
            )

    def _request(self, method, path, json=None, extra_headers=None):
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        try:
            resp = requests.request(method, f"{BASE}{path}", headers=headers, json=json, timeout=30)
        except requests.RequestException as exc:
            raise PayPalError("PayPal connection failed; the payment outcome may be unknown. "
                              "Check the existing transaction before retrying.") from exc
        self._raise_if_error(resp)
        return resp.json()

    # ---- money in: a member's contribution ----
    def create_order(self, amount, currency="USD", reference=None,
                     save_payment_method=False,
                     return_url="https://example.com/return",
                     cancel_url="https://example.com/cancel"):
        """Create a sandbox order (a contribution). A buyer must still approve it.

        save_payment_method=True asks PayPal to store the buyer's PayPal wallet in
        the Vault after a successful capture, so later rounds can be charged
        without the buyer clicking approve again.
        """
        unit = {"amount": {"currency_code": currency, "value": f"{amount:.2f}"}}
        if reference:
            unit["reference_id"] = reference
        body = {"intent": "CAPTURE", "purchase_units": [unit]}
        if save_payment_method:
            body["payment_source"] = {
                "paypal": {
                    "attributes": {
                        "vault": {
                            "store_in_vault": "ON_SUCCESS",
                            "usage_type": "MERCHANT",
                            "customer_type": "CONSUMER",
                        }
                    },
                    "experience_context": {"return_url": return_url, "cancel_url": cancel_url},
                }
            }
        order = self._request(
            "POST",
            "/v2/checkout/orders",
            json=body,
            extra_headers={"PayPal-Request-Id": str(uuid.uuid4())},
        )
        # A normal order labels its approval link "approve"; a vault order uses "payer-action".
        approve = next(
            (l["href"] for l in order.get("links", []) if l["rel"] in ("approve", "payer-action")),
            None,
        )
        return {"id": order["id"], "status": order["status"], "approve_url": approve}

    def capture_order(self, order_id, request_id=None):
        """Capture an order after the buyer has approved it."""
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture",
                             extra_headers={"PayPal-Request-Id": request_id or str(uuid.uuid4())})

    def create_vault_order(self, vault_id, amount, *, reference, request_id, mock_error=None):
        """Create only. The round journal saves this order ID before capture."""
        headers = {"PayPal-Request-Id": request_id}
        if mock_error:
            headers["PayPal-Mock-Response"] = json.dumps({"mock_application_codes": mock_error})
        return self._request("POST", "/v2/checkout/orders", json={
            "intent": "CAPTURE",
            "purchase_units": [{"reference_id": reference,
                                "amount": {"currency_code": "USD", "value": f"{amount:.2f}"}}],
            "payment_source": {"paypal": {"vault_id": vault_id}},
        }, extra_headers=headers)

    def charge_vaulted(self, vault_id, amount, currency="USD", reference=None, mock_error=None):
        """Charge a saved PayPal wallet with no buyer present (the member approved once).

        mock_error: sandbox-only test hook. Pass e.g. "INSTRUMENT_DECLINED" to ask
        PayPal to simulate that failure (documented for the sandbox; untested here).

        Returns {"id", "status", "raw"}. If PayPal refuses the charge this raises
        PayPalError, which Tanda can record as a missed payment (a 0 in the history).
        """
        unit = {"amount": {"currency_code": currency, "value": f"{amount:.2f}"}}
        if reference:
            unit["reference_id"] = reference
        headers = {"PayPal-Request-Id": str(uuid.uuid4())}
        if mock_error:
            headers["PayPal-Mock-Response"] = json.dumps({"mock_application_codes": mock_error})
        order = self._request(
            "POST",
            "/v2/checkout/orders",
            json={
                "intent": "CAPTURE",
                "purchase_units": [unit],
                "payment_source": {"paypal": {"vault_id": vault_id}},
            },
            extra_headers=headers,
        )
        # Some responses come back already COMPLETED; otherwise capture it.
        if order.get("status") != "COMPLETED":
            order = self.capture_order(order["id"])
        return {"id": order.get("id"), "status": order.get("status"), "raw": order}

    def get_order(self, order_id):
        return self._request("GET", f"/v2/checkout/orders/{order_id}")

    # ---- money out: the round's pot ----
    def send_payout(self, receiver_email, amount, note, currency="USD", sender_batch_id=None):
        """Send one payout. sender_batch_id must be unique for 30 days, so a default is generated."""
        batch_id = sender_batch_id or f"tanda-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        body = {
            "sender_batch_header": {
                "sender_batch_id": batch_id,
                "email_subject": "Tanda payout",
                "email_message": "Your savings circle payout",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "amount": {"value": f"{amount:.2f}", "currency": currency},
                    "receiver": receiver_email,
                    "note": note,
                    "sender_item_id": batch_id,
                }
            ],
        }
        data = self._request("POST", "/v1/payments/payouts", json=body)
        header = data["batch_header"]
        return {"payout_batch_id": header["payout_batch_id"], "batch_status": header["batch_status"]}

    def get_payout(self, payout_batch_id):
        """Check a payout's status (it can start as PENDING)."""
        data = self._request("GET", f"/v1/payments/payouts/{payout_batch_id}")
        header = data["batch_header"]
        return {"batch_status": header["batch_status"], "items": data.get("items", []),
                "payout_batch_id": header.get("payout_batch_id"),
                "sender_batch_id": header.get("sender_batch_header", {}).get("sender_batch_id")}


def extract_vault(order_json):
    """Pull the saved-payment-method info out of a captured order's response.

    PayPal's docs show the key as both 'attributes' and 'attribute', so check both.
    Returns {"vault_id", "status", "customer_id"}; vault_id can be None while the
    status is APPROVED (PayPal finishes saving it a moment later).
    """
    paypal = order_json.get("payment_source", {}).get("paypal", {})
    attrs = paypal.get("attributes") or paypal.get("attribute") or {}
    vault = attrs.get("vault", {})
    return {
        "vault_id": vault.get("id"),
        "status": vault.get("status"),
        "customer_id": vault.get("customer", {}).get("id"),
    }
