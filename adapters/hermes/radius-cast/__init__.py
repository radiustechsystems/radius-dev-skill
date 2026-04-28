from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_state import (
    current_session_id,
    get_session_provider,
    get_session_record,
    normalize_provider,
    post_tool_call,
    pre_tool_call,
    resolve_provider,
    set_session_provider,
    set_session_provider_error,
)


def _runtime_root() -> Path:
    explicit = str(os.environ.get("RADIUS_RUNTIME_ROOT") or "").strip()
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    skills_dir = str(os.environ.get("RADIUS_SKILLS_DIR") or "").strip()
    if skills_dir:
        candidates.append(Path(skills_dir).expanduser() / "runtimes" / "python")

    hermes_app_root = str(os.environ.get("HERMES_APP_ROOT") or "/app").strip()
    if hermes_app_root:
        candidates.append(
            Path(hermes_app_root).expanduser()
            / "vendor"
            / "radius-skills"
            / "runtimes"
            / "python"
        )

    here = Path(__file__).resolve().parent
    candidates.append(here.parents[2] / "runtimes" / "python")

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    searched = "\n".join(f"- {candidate}" for candidate in candidates)
    raise RuntimeError(
        "Unable to locate the shared Radius runtime for the Hermes radius-cast adapter.\n"
        "Set RADIUS_RUNTIME_ROOT explicitly or ensure the upstream Radius skills repo is "
        "available under RADIUS_SKILLS_DIR.\n"
        f"Searched:\n{searched}"
    )


_RUNTIME_ROOT = _runtime_root()
if str(_RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_ROOT))

from radius_wallet_runtime import RadiusWalletRuntime


_RUNTIME = RadiusWalletRuntime()


def _parse_provider_switch_request(message: str) -> str | None:
    text = str(message or "").strip().lower()
    if not text:
        return None
    patterns = (
        r"\buse\s+(para|local)\s+wallet\b",
        r"\buse\s+(para|local)\s+as\s+(?:the\s+)?wallet\b",
        r"\bswitch(?:\s+back)?\s+to\s+(para|local)\s+wallet\b",
        r"\bset\s+(?:the\s+)?wallet\s+provider\s+to\s+(para|local)\b",
        r"\bchange\s+(?:the\s+)?wallet\s+provider\s+to\s+(para|local)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _is_para_available() -> tuple[bool, str]:
    try:
        wallet = _RUNTIME.wallet_address(provider="para")
        return True, f"wallet {wallet['address']}"
    except Exception as err:
        return False, str(err)


def _provider_status_context(provider: str, session_id: str) -> str:
    record = get_session_record(session_id)
    error_line = ""
    if record.get("error"):
        error_line = f"- provider error: {record['error']}\n"
    return (
        f"Wallet provider status for this session:\n"
        f"- session_id: {session_id}\n"
        f"- default wallet provider: {provider}\n"
        f"{error_line}"
        f"- For Radius wallet tools, omit the provider argument when the user wants the session default.\n"
        f"- If the user explicitly asks for the local or para wallet in this turn, pass the provider argument "
        f"to `radius_wallet_address`, `radius_balance`, `radius_send_sbc`, or `radius_send_rusd`."
    )


def _effective_provider(params: dict | None, kwargs: dict | None = None) -> tuple[str, str]:
    params = params or {}
    kwargs = kwargs or {}
    session_id = current_session_id(kwargs)
    provider = resolve_provider(params.get("provider"), session_id=session_id)
    return provider, session_id


def register(ctx):
    def radius_pre_llm_call(session_id: str, user_message: str, **kwargs):
        switch_to = _parse_provider_switch_request(user_message)
        if switch_to:
            if switch_to == "para":
                available, reason = _is_para_available()
                if not available:
                    set_session_provider_error(session_id, "para", reason)
                    return {
                        "context": (
                            f"{_provider_status_context('para', session_id)}\n\n"
                            f"The user explicitly requested the para wallet for this session, but the para provider "
                            f"is unavailable: {reason}\n"
                            f"Treat this as a hard error. Do not silently fall back to the local wallet for default "
                            f"wallet actions in this session. Only use the local wallet if the user explicitly asks "
                            f"for it in this turn or explicitly switches the session back to local."
                        )
                    }
            provider = set_session_provider(session_id, switch_to)
            return {
                "context": (
                    f"{_provider_status_context(provider, session_id)}\n\n"
                    f"The user explicitly switched the session wallet provider to {provider}. "
                    f"Confirm the change in your response and use this provider as the default for wallet actions "
                    f"unless the user explicitly asks for the other provider in this turn."
                )
            }

        return {"context": _provider_status_context(get_session_provider(session_id), session_id)}

    def radius_on_session_start(session_id: str, **kwargs):
        set_session_provider(session_id, "local")

    def radius_wallet_address(params, **kwargs):
        provider, session_id = _effective_provider(params, kwargs)
        data = _RUNTIME.wallet_address(provider=provider)
        data["session_id"] = session_id or None
        return json.dumps(data)

    def radius_balance(params, **kwargs):
        provider, session_id = _effective_provider(params, kwargs)
        address = str((params or {}).get("address") or "").strip() or None
        data = _RUNTIME.balance(provider=provider, address=address)
        data["session_id"] = session_id or None
        return json.dumps(data)

    def radius_send_sbc(params, **kwargs):
        provider, session_id = _effective_provider(params, kwargs)
        to_address = str((params or {}).get("to") or "").strip()
        amount_sbc = str((params or {}).get("amount_sbc", "")).strip()
        if not to_address:
            return "Error: missing required parameter 'to'."
        if not amount_sbc:
            return "Error: missing required parameter 'amount_sbc'."
        network = str((params or {}).get("network") or "").strip() or None
        data = _RUNTIME.send_sbc(
            to_address=to_address,
            amount_sbc=amount_sbc,
            provider=provider,
            network=network,
        )
        data["session_id"] = session_id or None
        return json.dumps(data)

    def radius_send_rusd(params, **kwargs):
        provider, session_id = _effective_provider(params, kwargs)
        to_address = str((params or {}).get("to") or "").strip()
        amount_rusd = str((params or {}).get("amount_rusd", "")).strip()
        if not to_address:
            return "Error: missing required parameter 'to'."
        if not amount_rusd:
            return "Error: missing required parameter 'amount_rusd'."
        network = str((params or {}).get("network") or "").strip() or None
        data = _RUNTIME.send_rusd(
            to_address=to_address,
            amount_rusd=amount_rusd,
            provider=provider,
            network=network,
        )
        data["session_id"] = session_id or None
        return json.dumps(data)

    def radius_tx_status(params, **kwargs):
        tx_hash = str((params or {}).get("tx_hash") or "").strip()
        if not tx_hash:
            return "Error: missing required parameter 'tx_hash'."
        return json.dumps(_RUNTIME.tx_status(tx_hash))

    def radius_chain_info(params, **kwargs):
        return json.dumps(_RUNTIME.chain_info())

    ctx.register_hook("pre_llm_call", radius_pre_llm_call)
    ctx.register_hook("on_session_start", radius_on_session_start)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)

    ctx.register_tool(
        name="radius_wallet_address",
        toolset="radius-cast",
        schema={
            "name": "radius_wallet_address",
            "description": (
                "Return this agent's Radius wallet address for the selected provider. "
                "Defaults to the session wallet provider and supports explicit provider overrides."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "enum": ["local", "para"],
                        "description": (
                            "Optional wallet provider override. If omitted, the session wallet provider is used."
                        ),
                    }
                },
                "required": [],
            },
        },
        handler=radius_wallet_address,
    )

    ctx.register_tool(
        name="radius_balance",
        toolset="radius-cast",
        schema={
            "name": "radius_balance",
            "description": (
                "Get Radius balances for an address. Returns Radius RUSD native balance "
                "and SBC ERC-20 balance. If address is omitted, the selected provider wallet is used."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": (
                            "Optional address to inspect. If omitted, the selected provider wallet address is used."
                        ),
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["local", "para"],
                        "description": (
                            "Optional wallet provider override. If omitted, the session wallet provider is used."
                        ),
                    },
                },
                "required": [],
            },
        },
        handler=radius_balance,
    )

    ctx.register_tool(
        name="radius_send_sbc",
        toolset="radius-cast",
        schema={
            "name": "radius_send_sbc",
            "description": (
                "Send SBC on Radius to a recipient address. Uses the selected provider "
                "wallet and returns the tx hash plus explorer URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient EVM address.",
                    },
                    "amount_sbc": {
                        "type": "string",
                        "description": "Decimal SBC amount to send, for example '1.25'.",
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["local", "para"],
                        "description": (
                            "Optional wallet provider override. If omitted, the session wallet provider is used."
                        ),
                    },
                    "network": {
                        "type": "string",
                        "enum": ["testnet", "mainnet"],
                        "description": "Optional network override for this write. Defaults to runtime env/testnet.",
                    },
                },
                "required": ["to", "amount_sbc"],
            },
        },
        handler=radius_send_sbc,
    )

    ctx.register_tool(
        name="radius_send_rusd",
        toolset="radius-cast",
        schema={
            "name": "radius_send_rusd",
            "description": (
                "Send native RUSD on Radius to a recipient address. Uses the selected provider "
                "wallet and returns the tx hash plus explorer URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient EVM address.",
                    },
                    "amount_rusd": {
                        "type": "string",
                        "description": "Decimal RUSD amount to send, for example '0.001'.",
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["local", "para"],
                        "description": (
                            "Optional wallet provider override. If omitted, the session wallet provider is used."
                        ),
                    },
                    "network": {
                        "type": "string",
                        "enum": ["testnet", "mainnet"],
                        "description": "Optional network override for this write. Defaults to runtime env/testnet.",
                    },
                },
                "required": ["to", "amount_rusd"],
            },
        },
        handler=radius_send_rusd,
    )

    ctx.register_tool(
        name="radius_tx_status",
        toolset="radius-cast",
        schema={
            "name": "radius_tx_status",
            "description": "Fetch a Radius transaction receipt by hash.",
            "parameters": {
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
        handler=radius_tx_status,
    )

    ctx.register_tool(
        name="radius_chain_info",
        toolset="radius-cast",
        schema={
            "name": "radius_chain_info",
            "description": "Return the active Radius network configuration and live RPC metadata.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        handler=radius_chain_info,
    )
