#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any

try:
    from .radius_wallet_runtime import RadiusWalletRuntime
except ImportError:
    from radius_wallet_runtime import RadiusWalletRuntime


PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "radius-wallet", "version": "0.1.0"}


TOOLS = [
    {
        "name": "radius_wallet_address",
        "description": "Return the Radius wallet address for the selected provider.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["local", "para"],
                    "description": "Wallet provider override. Defaults to local.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "radius_balance",
        "description": "Get native RUSD and SBC balances for an address or the selected provider wallet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["local", "para"],
                    "description": "Wallet provider override. Defaults to local.",
                },
                "address": {
                    "type": "string",
                    "description": "Optional EVM address to inspect.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "radius_send_sbc",
        "description": "Send SBC using the selected provider wallet and return transaction metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["local", "para"],
                    "description": "Wallet provider override. Defaults to local.",
                },
                "to": {
                    "type": "string",
                    "description": "Recipient EVM address.",
                },
                "amount_sbc": {
                    "type": "string",
                    "description": "Decimal SBC amount, for example '1.25'.",
                },
            },
            "required": ["to", "amount_sbc"],
        },
    },
    {
        "name": "radius_send_rusd",
        "description": "Send native RUSD using the selected provider wallet and return transaction metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["local", "para"],
                    "description": "Wallet provider override. Defaults to local.",
                },
                "to": {
                    "type": "string",
                    "description": "Recipient EVM address.",
                },
                "amount_rusd": {
                    "type": "string",
                    "description": "Decimal RUSD amount, for example '0.001'.",
                },
            },
            "required": ["to", "amount_rusd"],
        },
    },
    {
        "name": "radius_tx_status",
        "description": "Fetch Radius transaction receipt status by transaction hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tx_hash": {
                    "type": "string",
                    "description": "Transaction hash to inspect.",
                }
            },
            "required": ["tx_hash"],
        },
    },
    {
        "name": "radius_chain_info",
        "description": "Return the active Radius network configuration and selected live RPC metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def _response(message_id: Any, result: dict | None = None, error: dict | None = None) -> dict:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result or {}
    return payload


def _tool_result(payload: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "structuredContent": payload,
    }


def _tool_error(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {"error": message},
        "isError": True,
    }


def _handle_tool_call(runtime: RadiusWalletRuntime, name: str, arguments: dict | None) -> dict:
    args = arguments or {}
    if name == "radius_wallet_address":
        return _tool_result(runtime.wallet_address(provider=args.get("provider", "local")))
    if name == "radius_balance":
        return _tool_result(
            runtime.balance(
                provider=args.get("provider", "local"),
                address=args.get("address"),
            )
        )
    if name == "radius_send_sbc":
        return _tool_result(
            runtime.send_sbc(
                to_address=str(args.get("to") or ""),
                amount_sbc=str(args.get("amount_sbc") or ""),
                provider=args.get("provider", "local"),
            )
        )
    if name == "radius_send_rusd":
        return _tool_result(
            runtime.send_rusd(
                to_address=str(args.get("to") or ""),
                amount_rusd=str(args.get("amount_rusd") or ""),
                provider=args.get("provider", "local"),
            )
        )
    if name == "radius_tx_status":
        return _tool_result(runtime.tx_status(str(args.get("tx_hash") or "")))
    if name == "radius_chain_info":
        return _tool_result(runtime.chain_info())
    return _tool_error(f"unknown tool: {name}")


def handle_message(runtime: RadiusWalletRuntime, message: dict) -> dict | None:
    method = message.get("method")
    message_id = message.get("id")

    if method == "initialize":
        return _response(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )

    if method == "ping":
        return _response(message_id, {})

    if method == "tools/list":
        return _response(message_id, {"tools": TOOLS})

    if method == "tools/call":
        params = message.get("params") or {}
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments")
        try:
            return _response(message_id, _handle_tool_call(runtime, name, arguments))
        except Exception as err:
            return _response(message_id, _tool_error(str(err)))

    if "id" not in message:
        return None

    return _response(
        message_id,
        error={"code": -32601, "message": f"Method not found: {method}"},
    )


def main() -> int:
    runtime = RadiusWalletRuntime()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as err:
            print(
                json.dumps(
                    _response(
                        None,
                        error={"code": -32700, "message": f"Parse error: {err}"},
                    )
                ),
                flush=True,
            )
            continue

        response = handle_message(runtime, message)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
