"""Save one member's PayPal wallet so later rounds can charge it without a click.

Run it once per member:
    python vault_test.py Ben sb-2cvpw53296693@personal.example.com
(the name, then that member's sandbox Personal email). If you give a name and
email, the result is saved to members.local.json automatically.

IMPORTANT: when the approval link opens, log in as THAT SAME sandbox account,
in a private window, and close the window afterward.
"""
import sys

from paypal_client import PayPalClient, extract_vault
from tanda_members import save_wallet

name = sys.argv[1] if len(sys.argv) > 1 else None
email = sys.argv[2] if len(sys.argv) > 2 else None

client = PayPalClient()

order = client.create_order(amount=5.00, reference="vault-test", save_payment_method=True)
print("Order ID:", order["id"])
print("Status:", order["status"])
if email:
    print(f"\nOpen this link in a PRIVATE window and log in as {email} (not any other account):")
else:
    print("\nOpen this link, log in as a sandbox PERSONAL account, and approve:")
print(order["approve_url"])

input("\nAfter you approve (the page may redirect to example.com, that's fine), press Enter here...")

result = client.capture_order(order["id"])
print("\nCapture status:", result.get("status"))

vault = extract_vault(result)
print("Vault status:", vault["status"])
print("Vault ID:", vault["vault_id"])
print("Customer ID:", vault["customer_id"])

if vault["vault_id"]:
    print("\nSUCCESS: the payment method was saved.")
    if name and email:
        save_wallet(name, email, vault["vault_id"], vault["customer_id"])
        print(f"Saved {name} to members.local.json")
    else:
        print("To save it automatically next time, run:  python vault_test.py NAME EMAIL")
elif vault["status"] == "APPROVED":
    print("\nPayPal is still saving it. Wait a few seconds and run this again, or tell me what you see.")
else:
    print("\nNo vault information came back. Paste the Capture status and Vault lines (not your Secret).")