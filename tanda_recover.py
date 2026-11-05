"""Read-only PayPal reconciliation after a lost creation response. Never sends money."""
import argparse

from paypal_client import PayPalClient, PayPalError
from tanda_payments import LiveCircle
from tanda_round import demo_members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--circle-id", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--contribution", type=float, default=5.0)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--member")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--order-id")
    group.add_argument("--payout-batch-id")
    args = parser.parse_args()
    if args.round < 1 or (args.order_id and not args.member):
        parser.error("--round must be positive; --order-id also requires --member")
    try:
        circle = LiveCircle(demo_members(args.seed), args.contribution, args.circle_id, PayPalClient())
        circle.reconcile(args.round - 1, member_name=args.member,
                         order_id=args.order_id, payout_batch_id=args.payout_batch_id)
    except (PayPalError, ValueError) as exc:
        parser.exit(1, f"Not reconciled: {exc}\n")
    print("Existing transaction matched and recorded. No payment was submitted.")
    print("Resume with the same circle ID, seed and contribution, then review and approve.")


if __name__ == "__main__":
    main()
