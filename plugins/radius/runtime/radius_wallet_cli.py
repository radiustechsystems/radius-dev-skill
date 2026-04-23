#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

try:
    from .radius_wallet_runtime import RadiusWalletRuntime
except ImportError:
    from radius_wallet_runtime import RadiusWalletRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shared deterministic Radius wallet runtime CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    wallet_address = subparsers.add_parser("wallet-address")
    wallet_address.add_argument("--provider", default="local")

    balance = subparsers.add_parser("balance")
    balance.add_argument("--provider", default="local")
    balance.add_argument("--address")

    send_sbc = subparsers.add_parser("send-sbc")
    send_sbc.add_argument("--provider", default="local")
    send_sbc.add_argument("--to", required=True)
    send_sbc.add_argument("--amount", required=True)

    send_rusd = subparsers.add_parser("send-rusd")
    send_rusd.add_argument("--provider", default="local")
    send_rusd.add_argument("--to", required=True)
    send_rusd.add_argument("--amount", required=True)

    tx_status = subparsers.add_parser("tx-status")
    tx_status.add_argument("--tx-hash", required=True)

    subparsers.add_parser("chain-info")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime = RadiusWalletRuntime()
    try:
        if args.command == "wallet-address":
            result = runtime.wallet_address(provider=args.provider)
        elif args.command == "balance":
            result = runtime.balance(provider=args.provider, address=args.address)
        elif args.command == "send-sbc":
            result = runtime.send_sbc(
                to_address=args.to,
                amount_sbc=args.amount,
                provider=args.provider,
            )
        elif args.command == "send-rusd":
            result = runtime.send_rusd(
                to_address=args.to,
                amount_rusd=args.amount,
                provider=args.provider,
            )
        elif args.command == "tx-status":
            result = runtime.tx_status(args.tx_hash)
        elif args.command == "chain-info":
            result = runtime.chain_info()
        else:
            parser.error(f"unsupported command: {args.command}")
            return 2
    except Exception as err:
        print(json.dumps({"error": str(err)}), file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
