from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch


TEST_ROOT = os.path.dirname(os.path.dirname(__file__))
if TEST_ROOT not in sys.path:
    sys.path.insert(0, TEST_ROOT)

from radius_wallet_mcp import handle_message
from radius_wallet_runtime import RadiusWalletRuntime, _format_units, _parse_units


class RadiusWalletRuntimeTests(unittest.TestCase):
    def test_parse_units_rounds_down(self):
        self.assertEqual(_parse_units("1.2345678", 6), 1234567)

    def test_format_units_strips_trailing_zeroes(self):
        self.assertEqual(_format_units(1234500, 6), "1.2345")

    def test_chain_info_uses_testnet_label(self):
        runtime = RadiusWalletRuntime()
        with patch.object(runtime, "_rpc_request", side_effect=["0x3ac58d00", "0x18ef65f2200"]):
            result = runtime.chain_info()
        self.assertEqual(result["network"], "testnet")
        self.assertEqual(result["chain_id"], "72344")
        self.assertEqual(result["gas_price_wei"], "986025216")

    def test_mcp_tools_list(self):
        runtime = RadiusWalletRuntime()
        response = handle_message(
            runtime,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        self.assertIsNotNone(response)
        self.assertIn("result", response)
        self.assertGreater(len(response["result"]["tools"]), 0)

    def test_mcp_chain_info_tool(self):
        runtime = RadiusWalletRuntime()
        with patch.object(runtime, "chain_info", return_value={"network": "testnet"}):
            response = handle_message(
                runtime,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "radius_chain_info", "arguments": {}},
                },
            )
        self.assertIsNotNone(response)
        self.assertFalse(response["result"].get("isError", False))
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured, {"network": "testnet"})


if __name__ == "__main__":
    unittest.main()
