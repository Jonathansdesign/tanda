"""Enroll a member's sandbox wallet, or read an existing enrollment order.

Each NEW enrollment makes a 5 USD sandbox purchase with payer approval.
--resume-order only reads a previous order; it never creates or captures a payment.
"""
import argparse

from paypal_client import PayPalClient, PayPalError, extract_vault
from tanda_members import save_wallet


def finish_wallet(order, name=None, email=None):
    """Save only a wallet from a completed order, with a matching payer if reported."""
    if order.get("status") != "COMPLETED":
        print("Order is not completed. Inspect the existing order before making more requests.")
        return False
    paypal = order.get("payment_source", {}).get("paypal", {})
    payer_email = paypal.get("email_address")
    if email and payer_email and payer_email.casefold() != email.casefold():
        raise ValueError("The approved payer does not match the member email. Mapping was not saved.")
    vault = extract_vault(order)
    print("Vault status:", vault["status"])
    if not vault["vault_id"]:
        print("Wallet saving is not finished. Keep this order ID and check it again with --resume-order.")
        return False
    if name and email:
        save_wallet(name, email, vault["vault_id"], vault["customer_id"])
        print(f"Saved {name} to members.local.json")
    else:
        print("Vault ID:", vault["vault_id"])
        print("To save a member mapping, supply NAME EMAIL with --resume-order and this order ID.")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?")
    parser.add_argument("email", nargs="?")
    parser.add_argument("--resume-order", help="read this existing order; no new purchase or capture")
    args = parser.parse_args(argv)
    if bool(args.name) != bool(args.email):
        parser.error("Supply both NAME and EMAIL, or neither.")
    client = PayPalClient()
    if args.resume_order:
        print("Reading existing order:", args.resume_order)
        return finish_wallet(client.get_order(args.resume_order), args.name, args.email)

    order = client.create_order(amount=5.00, reference="vault-test", save_payment_method=True)
    print("Order ID:", order["id"])
    print("Status:", order["status"])
    if not order.get("approve_url"):
        print("No approval URL returned. Inspect this existing order; do not start a new purchase to retry.")
        return False
    account = args.email or "the intended sandbox PERSONAL account"
    print(f"Open this URL in a PRIVATE window and log in as {account}:")
    print(order["approve_url"])
    input("After approving wallet saving, press Enter here to capture the 5 USD test purchase...")
    result = client.capture_order(order["id"])
    print("Capture status:", result.get("status"))
    print("For later status checks without another purchase, use --resume-order", order["id"])
    return finish_wallet(result, args.name, args.email)


if __name__ == "__main__":
    try:
        main()
    except (PayPalError, ValueError) as exc:
        raise SystemExit(str(exc))
