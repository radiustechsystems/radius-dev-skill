#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SKILLS = {"radius-dev", "x402", "dripping-faucet", "radius-agent-ops"}
EXPECTED_TOOLS = {
    "radius_wallet_address",
    "radius_balance",
    "radius_send_sbc",
    "radius_send_rusd",
    "radius_tx_status",
    "radius_chain_info",
}


class _HermesToolCtx:
    def __init__(self) -> None:
        self.tools: list[dict] = []
        self.hooks: list[tuple[str, object]] = []

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)

    def register_hook(self, name, callback) -> None:
        self.hooks.append((name, callback))


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HermesInstallLayoutTests(unittest.TestCase):
    def test_hermes_adapter_registers_expected_tools_from_source_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HERMES_HOME": str(Path(tmp) / ".hermes"),
                "RADIUS_SKILLS_DIR": str(REPO_ROOT),
                "RADIUS_RUNTIME_ROOT": str(REPO_ROOT / "runtime" / "python"),
            }
            with patch.dict(os.environ, env, clear=False):
                module = _load_module(
                    REPO_ROOT / "adapters" / "hermes" / "radius-cast" / "__init__.py",
                    "radius_cast_source_test",
                )
                ctx = _HermesToolCtx()
                module.register(ctx)

        registered = {tool["name"] for tool in ctx.tools}
        self.assertEqual(EXPECTED_TOOLS, registered)
        self.assertIn("pre_llm_call", {name for name, _callback in ctx.hooks})
        self.assertIn("on_session_start", {name for name, _callback in ctx.hooks})

    def test_hermes_adapter_registers_expected_tools_from_installed_plugin_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hermes_home = tmp_path / ".hermes"
            plugin_dir = hermes_home / "plugins" / "radius-cast"
            runtime_dir = tmp_path / "external-skills" / "radius-skills" / "runtime" / "python"
            shutil.copytree(REPO_ROOT / "adapters" / "hermes" / "radius-cast", plugin_dir)
            shutil.copytree(REPO_ROOT / "runtime" / "python", runtime_dir)

            env = {
                "HERMES_HOME": str(hermes_home),
                "RADIUS_SKILLS_DIR": str(tmp_path / "external-skills" / "radius-skills"),
            }
            with patch.dict(os.environ, env, clear=False):
                module = _load_module(plugin_dir / "__init__.py", "radius_cast_installed_test")
                ctx = _HermesToolCtx()
                module.register(ctx)

        registered = {tool["name"] for tool in ctx.tools}
        self.assertEqual(EXPECTED_TOOLS, registered)

    def test_radius_wallet_runtime_supports_mainnet_override_and_pending_receipts(self):
        sys.path.insert(0, str(REPO_ROOT / "runtime" / "python"))
        try:
            from radius_wallet_runtime import RadiusWalletRuntime
        finally:
            sys.path.pop(0)

        tx_hash = "0x" + "4" * 64
        runtime = RadiusWalletRuntime()
        with patch.object(runtime, "_rpc_request", return_value=None):
            pending = runtime.tx_status(tx_hash)
        self.assertEqual(pending["status_label"], "pending")
        self.assertEqual(pending["network"], "testnet")

        balance = {
            "address": "0x" + "1" * 40,
            "rusd": "0",
            "rusd_raw": "0",
            "sbc": "1",
            "sbc_raw": "1000000",
        }
        with (
            patch.object(RadiusWalletRuntime, "_signer_args", return_value=["--account", "radius-dev"]),
            patch.object(RadiusWalletRuntime, "_resolve_local_wallet_address", return_value="0x" + "1" * 40),
            patch.object(RadiusWalletRuntime, "_cast_balance", return_value=balance),
            patch.object(RadiusWalletRuntime, "_run_cast", return_value=tx_hash) as run_cast,
            patch.object(RadiusWalletRuntime, "_wait_for_receipt", return_value=None),
        ):
            result = runtime.send_sbc("0x" + "2" * 40, "1", network="mainnet")

        self.assertEqual(result["network"], "mainnet")
        self.assertEqual(result["explorer_url"], f"https://network.radiustech.xyz/tx/{tx_hash}")
        self.assertIn("https://rpc.radiustech.xyz", run_cast.call_args.args[0])
        self.assertNotIn("--private-key", run_cast.call_args.args[0])

    def test_portable_skills_runtime_and_claude_root_payload_are_complete_without_duplication(self):
        for skill_name in EXPECTED_SKILLS:
            self.assertTrue((REPO_ROOT / "skills" / skill_name / "SKILL.md").exists(), skill_name)

        for runtime_file in ("__init__.py", "radius_wallet_cli.py", "radius_wallet_mcp.py", "radius_wallet_runtime.py"):
            self.assertTrue((REPO_ROOT / "runtime" / "python" / runtime_file).exists(), runtime_file)

        self.assertTrue((REPO_ROOT / ".claude-plugin" / "plugin.json").exists())
        self.assertTrue((REPO_ROOT / ".mcp.json").exists())
        self.assertFalse((REPO_ROOT / "adapters" / "claude-code" / "skills").exists())
        self.assertFalse((REPO_ROOT / "adapters" / "claude-code" / "runtime").exists())
        self.assertFalse((REPO_ROOT / "adapters" / "claude-code" / "runtimes").exists())

        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["plugins"][0]["source"], ".")
        mcp = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(
            mcp["mcp"]["servers"]["radius"]["args"],
            ["${CLAUDE_PLUGIN_ROOT}/runtime/python/radius_wallet_mcp.py"],
        )

    def test_tool_schema_and_mcp_surface_stay_in_sync(self):
        sys.path.insert(0, str(REPO_ROOT / "runtime" / "python"))
        try:
            import radius_wallet_mcp
        finally:
            sys.path.pop(0)
        schema = json.loads((REPO_ROOT / "spec" / "tools.schema.json").read_text(encoding="utf-8"))
        schema_tools = {tool["name"]: tool for tool in schema["tools"]}
        mcp_tools = {tool["name"]: tool for tool in radius_wallet_mcp.TOOLS}
        self.assertEqual(set(schema_tools), set(mcp_tools))
        for name in ("radius_send_sbc", "radius_send_rusd"):
            self.assertIn("network", schema_tools[name]["inputSchema"]["properties"])
            self.assertIn("network", mcp_tools[name]["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
