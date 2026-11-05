"""Durable, local-only sandbox round execution. No AI tools can call this module.

An intent is saved BEFORE a payment request. If a response is lost, we stop;
we do not assume a decline or replay an uncertain money-moving request.
"""
import hashlib
import json
import os
import re
import math
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from paypal_client import PayPalError


class RoundBlocked(PayPalError):
    pass


def completed_order(order, amount, reference):
    units = order.get("purchase_units", [])
    captures = [c for u in units for c in u.get("payments", {}).get("captures", [])]
    return (order.get("status") == "COMPLETED" and len(units) == 1
            and units[0].get("reference_id") == reference
            and bool(captures) and all(c.get("status") == "COMPLETED" for c in captures)
            and all(c.get("amount", {}).get("currency_code") == "USD" for c in captures)
            and sum(Decimal(c["amount"]["value"]) for c in captures) == Decimal(str(amount)))


class LiveCircle:
    """One circle ID, one immutable configuration, one persisted sandbox ledger."""

    def __init__(self, members, contribution, circle_id, client, directory=None):
        if not circle_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", circle_id):
            raise RoundBlocked("Choose a sandbox circle ID (1–64 letters, digits, _ or -). "
                               "Reuse that ID to resume this circle.")
        if not members or any(not m.vault_id or not m.email for m in members):
            raise RoundBlocked("Live sandbox mode requires a saved wallet AND payout email "
                               "for every member. Simulated contributions cannot fund a payout.")
        if len({m.name for m in members}) != len(members):
            raise RoundBlocked("Member names must be unique.")
        if len({m.vault_id for m in members}) != len(members):
            raise RoundBlocked("Each member must have a different saved wallet.")
        if not math.isfinite(contribution) or contribution <= 0 or round(contribution, 2) != contribution:
            raise RoundBlocked("Contribution must be positive and have at most two decimal places.")
        self.members, self.contribution, self.client = members, contribution, client
        self.circle_id = circle_id
        self.directory = Path(directory or Path(__file__).parent / ".tanda-local")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"{circle_id}.json"
        config = {"members": [(m.name, m.email, m.vault_id, m.history) for m in members],
                  "contribution": contribution, "merchant": getattr(client, "client_id", "")}
        self.fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

    @contextmanager
    def locked(self):
        # OS locks are released automatically after a crash. Never unlink the lock file.
        lock = open(self.directory / f"{self.circle_id}.lock", "a+b")
        acquired = False
        try:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                raise RoundBlocked("This circle is busy in another process. No new payment was started.") from exc
            if self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                if self.data.get("fingerprint") != self.fingerprint:
                    raise RoundBlocked("This circle ID already belongs to a different configuration. "
                                       "Restore its original settings to resume it.")
            else:
                self.data = {"version": 1, "fingerprint": self.fingerprint, "operations": {},
                             "ledger": [], "paid_out": [],
                             "histories": {m.name: list(m.history) for m in self.members}}
                self.save()
            yield
        finally:
            if acquired:
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def save(self):
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.path)

    def key(self, operation):
        return "tanda-" + hashlib.sha256(f"{self.circle_id}:{operation}".encode()).hexdigest()[:30]

    def restore(self):
        with self.locked():
            for m in self.members:
                m.history[:] = self.data["histories"][m.name]
            return list(self.data["paid_out"]), list(self.data["ledger"])

    def reconcile(self, rnd, *, member_name=None, order_id=None, payout_batch_id=None):
        """Attach a known transaction after a lost response, using read-only API calls.

        The reference/recipient/amount must match this journal. A bare assertion of
        payment success is never accepted. This does not submit or capture anything.
        """
        with self.locked():
            if rnd != len(self.data["ledger"]):
                raise RoundBlocked("Only the current unresolved round can be reconciled.")
            if order_id:
                member = next((m for m in self.members if m.name == member_name), None)
                key = f"r{rnd + 1}:{member_name}:create"
                op = self.data["operations"].get(key)
                if member is None or not op or op["state"] not in ("started", "unknown"):
                    raise RoundBlocked("No uncertain order-creation operation matches this member.")
                order = self.client.get_order(order_id)
                units = order.get("purchase_units", [])
                if (len(units) != 1 or units[0].get("reference_id") != self.key(key)
                        or units[0].get("amount", {}).get("currency_code") != "USD"
                        or Decimal(units[0]["amount"]["value"]) != Decimal(str(self.contribution))):
                    raise RoundBlocked("Order reference or amount does not match this operation.")
                self.data["operations"][key] = {"state": "done", "id": order_id,
                                               "request_id": self.key(key), "status": order.get("status")}
            elif payout_batch_id:
                key = f"r{rnd + 1}:payout"
                op = self.data["operations"].get(key)
                if not op or op["state"] not in ("started", "unknown"):
                    raise RoundBlocked("No uncertain payout operation matches this round.")
                result = self.client.get_payout(payout_batch_id)
                if result.get("sender_batch_id") != self.key(key):
                    raise RoundBlocked("Payout sender_batch_id does not match this operation.")
                self.data["operations"][key] = {"state": "done", "id": payout_batch_id,
                                               "request_id": self.key(key),
                                               "status": result.get("batch_status")}
            else:
                raise RoundBlocked("Provide an order ID or a payout batch ID.")
            self.save()

    def write_request(self, key, action):
        op = self.data["operations"].get(key)
        if op:
            if op["state"] in ("done", "declined"):
                return op
            if op["state"] != "rejected":
                raise RoundBlocked(f"Operation {key} has an uncertain outcome. "
                                   "Reconcile the existing PayPal transaction before continuing.")
        self.data["operations"][key] = {"state": "started", "request_id": self.key(key)}
        self.save()
        try:
            result = action(self.key(key))
        except PayPalError as exc:
            state = "declined" if exc.declined else "rejected" if exc.rejected else "unknown"
            self.data["operations"][key]["state"] = state
            self.save()
            if state == "declined":
                return self.data["operations"][key]
            raise RoundBlocked(f"Operation {key} stopped: {exc}") from exc
        # Save only IDs/status. Never persist API keys, wallet IDs or access tokens.
        op = {"state": "done", "request_id": self.key(key),
              "id": result.get("id") or result.get("payout_batch_id"),
              "status": result.get("status") or result.get("batch_status")}
        self.data["operations"][key] = op
        self.save()
        return op

    def charge(self, member, rnd, received, mock_decline):
        key = f"r{rnd + 1}:{member.name}:create"
        reference = self.key(key)
        create = self.write_request(key, lambda request_id: self.client.create_vault_order(
            member.vault_id, self.contribution, reference=reference, request_id=request_id,
            mock_error="INSTRUMENT_DECLINED" if mock_decline and received else None))
        if create["state"] == "declined":
            return False
        if not create.get("id"):
            raise RoundBlocked(f"No order ID for {member.name}. Reconcile before continuing.")
        # Read first: a previous capture may have succeeded even if its response was lost.
        order = self.client.get_order(create["id"])
        if completed_order(order, self.contribution, reference):
            return True
        capture_key = f"r{rnd + 1}:{member.name}:capture"
        capture = self.data["operations"].get(capture_key)
        if capture and capture["state"] == "declined":
            return False
        if order.get("status") != "APPROVED":
            raise RoundBlocked(f"Order for {member.name} is {order.get('status', 'unknown')}; "
                               "no confirmed contribution is counted.")
        capture = self.write_request(capture_key, lambda request_id:
                                     self.client.capture_order(create["id"], request_id=request_id))
        if capture["state"] == "declined":
            return False
        order = self.client.get_order(create["id"])
        if not completed_order(order, self.contribution, reference):
            raise RoundBlocked(f"Capture for {member.name} is not confirmed complete. "
                               "No payout has been started.")
        return True

    def execute(self, members, paid_out, rnd, winner, mock_decline=False, say=print):
        with self.locked():
            if rnd != len(self.data["ledger"]) or paid_out != self.data["paid_out"]:
                raise RoundBlocked("Circle state changed. Reload/resume this circle before approving.")
            outcomes = {}
            for member in members:
                outcomes[member.name] = self.charge(member, rnd, member.name in paid_out, mock_decline)
                say(f"  {member.name:6} {'paid' if outcomes[member.name] else 'DECLINED'} (PayPal sandbox)")
            pot = round(sum(outcomes.values()) * self.contribution, 2)
            payout_key = f"r{rnd + 1}:payout"
            if pot <= 0:
                raise RoundBlocked("No confirmed contributions; this round remains unresolved.")
            payout = self.write_request(payout_key, lambda request_id: self.client.send_payout(
                winner.email, pot, note=f"Tanda round {rnd + 1}", sender_batch_id=request_id))
            if not payout.get("id"):
                raise RoundBlocked("Payout has no batch ID. Reconcile before continuing.")
            result = self.client.get_payout(payout["id"])
            items = result.get("items", [])
            item = items[0].get("payout_item", {}) if len(items) == 1 else {}
            success = (result.get("batch_status") == "SUCCESS" and len(items) == 1
                       and items[0].get("transaction_status") == "SUCCESS"
                       and item.get("receiver") == winner.email
                       and item.get("amount", {}).get("currency") == "USD"
                       and Decimal(item.get("amount", {}).get("value", "-1")) == Decimal(str(pot)))
            if not success:
                raise RoundBlocked(f"Payout {payout['id']} is {result.get('batch_status', 'unknown')}. "
                                   "Winner is not marked paid. Approve again later to check this "
                                   "same batch; contributions will not be recreated.")
            missed = [m.name for m in members if m.name in paid_out and not outcomes[m.name]]
            histories = {name: list(history) for name, history in self.data["histories"].items()}
            for member in members:
                if member.name in paid_out:
                    histories[member.name].append(int(outcomes[member.name]))
            record = {"round": rnd + 1, "winner": winner.name, "pot": pot,
                      "missed_by_paid_members": missed,
                      "payout": f"confirmed, batch {payout['id']} (SUCCESS)"}
            self.data["histories"] = histories
            self.data["paid_out"].append(winner.name)
            self.data["ledger"].append(record)
            self.save()
            for member in members:
                member.history[:] = histories[member.name]
            paid_out.append(winner.name)
            say(f"Pot: ${pot:.2f}. Payout to {winner.name}: {record['payout']}")
            return record
