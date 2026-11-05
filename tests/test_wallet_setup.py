"""Wallet enrollment status checks must not create another test purchase."""
import unittest
from unittest.mock import Mock, patch

import vault_test


def order(status="COMPLETED", vault_id="test-wallet", email="ana@example.test"):
    return {"status": status, "payment_source": {"paypal": {
        "email_address": email,
        "attributes": {"vault": {"id": vault_id, "status": "VAULTED" if vault_id else "APPROVED",
                                   "customer": {"id": "test-customer"}}}}}}


class WalletSetupTests(unittest.TestCase):
    def test_resume_reads_without_creating_or_capturing(self):
        client = Mock()
        client.get_order.return_value = order()
        with patch.object(vault_test, "PayPalClient", return_value=client), \
                patch.object(vault_test, "save_wallet") as save:
            self.assertTrue(vault_test.main(["Ana", "ana@example.test", "--resume-order", "existing-order"]))
            save.assert_called_once_with("Ana", "ana@example.test", "test-wallet", "test-customer")
        client.get_order.assert_called_once_with("existing-order")
        client.create_order.assert_not_called()
        client.capture_order.assert_not_called()

    def test_pending_wallet_is_not_saved(self):
        with patch.object(vault_test, "save_wallet") as save:
            self.assertFalse(vault_test.finish_wallet(order(vault_id=None), "Ana", "ana@example.test"))
            save.assert_not_called()

    def test_incomplete_purchase_is_not_saved(self):
        with patch.object(vault_test, "save_wallet") as save:
            self.assertFalse(vault_test.finish_wallet(order(status="APPROVED"), "Ana", "ana@example.test"))
            save.assert_not_called()

    def test_wrong_personal_account_is_not_saved(self):
        with patch.object(vault_test, "save_wallet") as save:
            with self.assertRaises(ValueError):
                vault_test.finish_wallet(order(email="ben@example.test"), "Ana", "ana@example.test")
            save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
