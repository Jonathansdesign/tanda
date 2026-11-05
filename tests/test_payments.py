"""Payment state and recovery regression tests. No API keys or network needed."""
import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paypal_client import PayPalClient, PayPalError
from tanda_payments import LiveCircle, RoundBlocked
from tanda_round import Member
from tanda_tools import TandaSession, call_tool, new_demo_session


class FakeClient:
    client_id = "fake-merchant"

    def __init__(self):
        self.orders, self.payouts, self.calls = {}, {}, []
        self.create_errors = {}
        self.capture_errors = {}
        self.lose_create = False
        self.lose_capture = False
        self.lose_payout = False
        self.payout_status = "SUCCESS"
        self.item_status = "SUCCESS"

    def create_vault_order(self, vault_id, amount, *, reference, request_id, mock_error=None):
        self.calls.append(("create", vault_id, request_id))
        if vault_id in self.create_errors:
            raise self.create_errors[vault_id]
        order_id = f"ORDER-{len(self.orders) + 1}"
        self.orders[order_id] = {"id": order_id, "status": "APPROVED", "purchase_units": [{
            "reference_id": reference, "amount": {"currency_code": "USD", "value": f"{amount:.2f}"}}]}
        if self.lose_create:
            self.lose_create = False
            raise PayPalError("Creation response lost")
        return copy.deepcopy(self.orders[order_id])

    def get_order(self, order_id):
        return copy.deepcopy(self.orders[order_id])

    def capture_order(self, order_id, request_id=None):
        self.calls.append(("capture", order_id, request_id))
        if order_id in self.capture_errors:
            raise self.capture_errors[order_id]
        order = self.orders[order_id]
        order["status"] = "COMPLETED"
        order["purchase_units"][0]["payments"] = {"captures": [{"id": "CAP-" + order_id,
            "status": "COMPLETED", "amount": order["purchase_units"][0]["amount"]}]}
        if self.lose_capture:
            self.lose_capture = False
            raise PayPalError("Capture response lost")
        return copy.deepcopy(order)

    def send_payout(self, receiver_email, amount, note, sender_batch_id=None):
        self.calls.append(("payout", receiver_email, sender_batch_id))
        batch_id = f"BATCH-{len(self.payouts) + 1}"
        self.payouts[batch_id] = {"payout_batch_id": batch_id, "batch_status": self.payout_status,
            "sender_batch_id": sender_batch_id, "items": [{"transaction_status": self.item_status,
            "payout_item": {"receiver": receiver_email, "amount": {"currency": "USD", "value": f"{amount:.2f}"}}}]}
        if self.lose_payout:
            self.lose_payout = False
            raise PayPalError("Payout response lost")
        return {"payout_batch_id": batch_id, "batch_status": self.payout_status}

    def get_payout(self, batch_id):
        return copy.deepcopy(self.payouts[batch_id])


def members():
    return [Member("Ana", [1] * 8, email="ana@example.test", vault_id="WALLET-A"),
            Member("Ben", [1, 0] * 4, email="ben@example.test", vault_id="WALLET-B")]


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = FakeClient()

    def session(self):
        return TandaSession(members(), live=True, client=self.client,
                            circle_id="test-circle", journal_dir=self.temp.name)

    def approve(self, session):
        proposal = session.propose_next_round()
        return session.approve_and_run(proposal["proposal_id"])

    def test_happy_path_and_persistent_resume(self):
        s = self.session()
        result = self.approve(s)
        self.assertNotIn("error", result)
        self.assertEqual(result["pot"], 10)
        restarted = self.session()
        self.assertEqual(restarted.rnd, 1)
        self.assertEqual(restarted.paid_out, ["Ana"])
        self.assertEqual(self.client.calls.count(("payout", "ana@example.test",
                          s.live_journal.key("r1:payout"))), 1)

    def test_pending_payout_never_advances_or_recollects(self):
        self.client.payout_status = "PENDING"
        s = self.session()
        self.assertIn("error", self.approve(s))
        self.assertEqual((s.rnd, s.paid_out), (0, []))
        self.assertIsNotNone(s.pending)
        before = list(self.client.calls)
        self.assertIn("error", self.approve(self.session()))
        self.assertEqual(self.client.calls, before)
        self.client.payouts["BATCH-1"]["batch_status"] = "SUCCESS"
        self.assertNotIn("error", self.approve(self.session()))
        self.assertEqual(self.client.calls, before)

    def test_failed_payout_never_marks_winner_paid(self):
        self.client.payout_status = "DENIED"
        self.client.item_status = "FAILED"
        s = self.session()
        self.assertIn("error", self.approve(s))
        self.assertEqual(s.paid_out, [])
        self.assertEqual(s.rnd, 0)

    def test_success_batch_with_failed_item_is_not_paid(self):
        self.client.item_status = "FAILED"
        s = self.session()
        self.assertIn("error", self.approve(s))
        self.assertEqual(s.paid_out, [])

    def test_partial_collection_auth_error_then_resume_skips_first_charge(self):
        self.client.create_errors["WALLET-B"] = PayPalError("Auth error", rejected=True)
        s = self.session()
        self.assertIn("error", self.approve(s))
        self.assertEqual(s.members[0].history, [1] * 8)
        self.assertFalse(any(c[0] == "payout" for c in self.client.calls))
        self.client.create_errors.clear()
        self.assertNotIn("error", self.approve(self.session()))
        self.assertEqual(sum(c[:2] == ("create", "WALLET-A") for c in self.client.calls), 1)
        ben_keys = [c[2] for c in self.client.calls if c[:2] == ("create", "WALLET-B")]
        self.assertEqual(len(set(ben_keys)), 1)

    def test_lost_create_response_requires_read_only_reconciliation(self):
        self.client.lose_create = True
        s = self.session()
        self.assertIn("error", self.approve(s))
        before = list(self.client.calls)
        self.assertIn("error", self.approve(self.session()))
        self.assertEqual(before, self.client.calls)
        resumed = self.session()
        resumed.live_journal.reconcile(0, member_name="Ana", order_id="ORDER-1")
        self.assertEqual(before, self.client.calls)
        self.assertNotIn("error", self.approve(resumed))
        self.assertEqual(sum(c[0] == "create" for c in self.client.calls), 2)

    def test_reconciliation_rejects_unrelated_order(self):
        self.client.lose_create = True
        s = self.session()
        self.approve(s)
        self.client.orders["ORDER-1"]["purchase_units"][0]["reference_id"] = "unrelated"
        with self.assertRaises(RoundBlocked):
            s.live_journal.reconcile(0, member_name="Ana", order_id="ORDER-1")

    def test_lost_capture_response_recovers_using_existing_order(self):
        self.client.lose_capture = True
        s = self.session()
        self.assertIn("error", self.approve(s))
        self.assertNotIn("error", self.approve(self.session()))
        self.assertEqual(sum(c[:2] == ("capture", "ORDER-1") for c in self.client.calls), 1)

    def test_lost_payout_response_does_not_resend(self):
        self.client.lose_payout = True
        s = self.session()
        self.assertIn("error", self.approve(s))
        before = list(self.client.calls)
        self.assertIn("error", self.approve(self.session()))
        self.assertEqual(before, self.client.calls)
        resumed = self.session()
        resumed.live_journal.reconcile(0, payout_batch_id="BATCH-1")
        self.assertNotIn("error", self.approve(resumed))
        self.assertEqual(before, self.client.calls)

    def test_missing_wallet_rejected_before_any_payment(self):
        ms = members()
        ms[1].vault_id = None
        with self.assertRaises(RoundBlocked):
            LiveCircle(ms, 5, "bad", self.client, self.temp.name)
        self.assertEqual(self.client.calls, [])

    def test_missing_recipient_and_duplicate_wallet_rejected(self):
        for field, value in [("email", None), ("vault_id", "WALLET-A")]:
            ms = members()
            setattr(ms[1], field, value)
            with self.assertRaises(RoundBlocked):
                LiveCircle(ms, 5, "bad", self.client, self.temp.name)

    def test_configuration_cannot_change_when_resuming(self):
        s = self.session()
        with self.assertRaises(RoundBlocked):
            TandaSession(members(), contribution=6, live=True, client=self.client,
                         circle_id="test-circle", journal_dir=self.temp.name)

    def test_concurrent_operator_is_blocked(self):
        s = self.session()
        with s.live_journal.locked():
            with self.assertRaises(RoundBlocked):
                self.session()
        self.assertEqual(self.client.calls, [])

    def test_crash_after_final_commit_resumes_completed_round_without_new_payments(self):
        s = self.session()
        original_save = s.live_journal.save
        def crash_after_commit():
            original_save()
            if s.live_journal.data["ledger"]:
                raise RuntimeError("Process interrupted after durable final commit")
        with patch.object(s.live_journal, "save", side_effect=crash_after_commit):
            self.assertIn("error", self.approve(s))
        before = list(self.client.calls)
        resumed = self.session()
        self.assertEqual(resumed.rnd, 1)
        self.assertEqual(resumed.paid_out, ["Ana"])
        self.assertEqual(before, self.client.calls)

    def test_payout_with_wrong_recipient_does_not_advance(self):
        original = self.client.get_payout
        def wrong_recipient(batch_id):
            result = original(batch_id)
            result["items"][0]["payout_item"]["receiver"] = "other@example.test"
            return result
        self.client.get_payout = wrong_recipient
        s = self.session()
        self.assertIn("error", self.approve(s))
        self.assertEqual(s.paid_out, [])

    def test_unknown_outcome_does_not_change_reliability(self):
        s = self.session()
        self.approve(s)
        before = list(s.members[0].history)
        self.client.create_errors["WALLET-A"] = PayPalError("Service unavailable")
        self.assertIn("error", self.approve(s))
        self.assertEqual(s.members[0].history, before)
        self.assertEqual(s.rnd, 1)

    def test_confirmed_decline_updates_history_only_once(self):
        s = self.session()
        self.approve(s)
        self.client.create_errors["WALLET-A"] = PayPalError("Declined", declined=True, rejected=True)
        self.client.payout_status = "PENDING"
        self.assertIn("error", self.approve(s))
        self.assertEqual(len(s.members[0].history), 8)
        self.client.payouts["BATCH-2"]["batch_status"] = "SUCCESS"
        self.assertNotIn("error", self.approve(s))
        self.assertEqual(s.members[0].history, [1] * 8 + [0])
        self.assertEqual(s.ledger[1]["pot"], 5)
        self.assertEqual(self.session().members[0].history, [1] * 8 + [0])

    def test_incomplete_capture_is_not_counted(self):
        original = self.client.capture_order
        def capture(order_id, request_id=None):
            result = original(order_id, request_id)
            self.client.orders[order_id]["status"] = "PENDING"
            return result
        self.client.capture_order = capture
        s = self.session()
        self.assertIn("error", self.approve(s))
        self.assertFalse(any(c[0] == "payout" for c in self.client.calls))

    def test_journal_contains_no_wallet_or_email(self):
        s = self.session()
        self.approve(s)
        text = Path(self.temp.name, "test-circle.json").read_text()
        self.assertNotIn("WALLET-A", text)
        self.assertNotIn("@example.test", text)

    def test_ai_cannot_approve(self):
        s = self.session()
        result = call_tool(s, "approve_and_run", {})
        self.assertIn("error", result)
        self.assertEqual(self.client.calls, [])

    def test_stale_proposal_does_nothing(self):
        s = self.session()
        s.propose_next_round()
        self.assertIn("error", s.approve_and_run("wrong-id"))
        self.assertEqual(self.client.calls, [])

    def test_dry_run_numbers_and_flow_unchanged(self):
        with patch("tanda_round.load_wallets", return_value={}), patch.dict("os.environ", {}, clear=True):
            s = new_demo_session()
        score = s.score_orders()
        self.assertEqual(score["expected_loss"], 13.10)
        self.assertEqual(score["random_order_expected_loss"], 21.31)
        self.assertEqual(s.propose_next_round(), s.propose_next_round())
        self.assertEqual(s.score_orders()["expected_loss"], 13.10)
        for _ in range(6):
            self.assertNotIn("error", self.approve(s))
        self.assertTrue(s.complete)
        self.assertEqual(sum(len(r["missed_by_paid_members"]) for r in s.ledger), 4)


class ClientTests(unittest.TestCase):
    def test_error_classification(self):
        cases = [(401, {"name": "AUTHENTICATION_FAILURE"}, False, True),
                 (500, {"name": "INTERNAL_SERVER_ERROR"}, False, False),
                 (422, {"details": [{"issue": "INSTRUMENT_DECLINED"}]}, True, True)]
        for status, body, declined, rejected in cases:
            response = unittest.mock.Mock(status_code=status)
            response.json.return_value = body
            with self.assertRaises(PayPalError) as result:
                PayPalClient._raise_if_error(response)
            self.assertEqual((result.exception.declined, result.exception.rejected), (declined, rejected))

    def test_stable_request_ids_reach_adapter(self):
        client = PayPalClient("fake", "fake")
        with patch.object(client, "_request", return_value={}) as request:
            client.create_vault_order("test-wallet", 5, reference="ref", request_id="stable-create")
            self.assertEqual(request.call_args.kwargs["extra_headers"]["PayPal-Request-Id"], "stable-create")
            client.capture_order("order", request_id="stable-capture")
            self.assertEqual(request.call_args.kwargs["extra_headers"]["PayPal-Request-Id"], "stable-capture")


if __name__ == "__main__":
    unittest.main()
