"""Remembers which sandbox account belongs to which circle member.

Saved in members.local.json next to the code. That file is listed in .gitignore
so it stays on your computer. Each entry looks like:
    "Ben": {"email": "sb-...@personal.example.com", "vault_id": "...", "customer_id": "..."}
The vault_id is the saved PayPal wallet that vault_test.py created.
"""
import json
import os

MEMBERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "members.local.json")


def load_wallets(path=MEMBERS_FILE):
    """Return {name: {...}}. An empty dict if the file doesn't exist yet."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_wallet(name, email, vault_id, customer_id=None, path=MEMBERS_FILE):
    """Add or update one member, keeping everyone else already in the file."""
    wallets = load_wallets(path)
    wallets[name] = {"email": email, "vault_id": vault_id, "customer_id": customer_id}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wallets, f, indent=2)
    return wallets
