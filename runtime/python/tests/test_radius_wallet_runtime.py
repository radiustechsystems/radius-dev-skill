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
from radius_wallet_runtime import GasFeeEstimate, RadiusWalletRuntime, _format_units, _parse_units


FROM_ADDRESS = "0x" + "1" * 40
TO_ADDRESS = "0x" + "2" * 40
PRIVATE_KEY = "0x" + "3" * 64
TX_HASH = "0x" + "4" * 64
ONE_RUSD_WEI = 10**18


class RadiusWalletRuntimeTests(unittest.TestCase):
    def test_parse_units_rejects_over_precision(self):
        with self.assertRaisesRegex(ValueError, "too many decimal places"):
            _parse_units("1.2345678", 6)
        with self.assertRaisesRegex(ValueError, "too many decimal places"):
            _parse_units("1.2345670", 6)

    def test_parse_units_rejects_amount_below_base_unit(self):
        with self.assertRaisesRegex(ValueError, "below the smallest base unit"):
            _parse_units("0.0000001", 6)

    def test_parse_units_accepts_supported_precision(self):
        self.assertEqual(_parse_units("1.234567", 6), 1234567)

    def test_format_units_strips_trailing_zeroes(self):
        self.assertEqual(_format_units(1234500, 6), "1.2345")

    def test_send_rusd_local_defers_gas_to_cast(self):
        runtime = RadiusWalletRuntime()
        balance = {
            "address": FROM_ADDRESS,
            "rusd": "1",
            "rusd_raw": str(ONE_RUSD_WEI),
            "sbc": "0",
            "sbc_raw": "0",
        }
        with (
            patch.object(runtime, "_signer_args", return_value=["--account", "radius-dev"]),
            patch.object(runtime, "_resolve_local_wallet_address", return_value=FROM_ADDRESS),
            patch.object(runtime, "_cast_balance", return_value=balance),
            patch.object(runtime, "_run_cast", return_value=TX_HASH) as run_cast,
            patch.object(runtime, "_wait_for_receipt", return_value=None),
            patch.object(runtime, "_rpc_request") as rpc_request,
        ):
            result = runtime.send_rusd(TO_ADDRESS, "1")

        send_args = run_cast.call_args.args[0]
        self.assertNotIn("--gas-limit", send_args)
        self.assertNotIn("--gas-price", send_args)
        self.assertNotIn("--private-key", send_args)
        self.assertIn("--account", send_args)
        self.assertEqual(result["tx_hash"], TX_HASH)
        rpc_request.assert_not_called()

    def test_send_sbc_local_defers_gas_to_cast(self):
        runtime = RadiusWalletRuntime()
        balance = {
            "address": FROM_ADDRESS,
            "rusd": "0",
            "rusd_raw": "0",
            "sbc": "1",
            "sbc_raw": "1000000",
        }
        with (
            patch.object(runtime, "_signer_args", return_value=["--account", "radius-dev"]),
            patch.object(runtime, "_resolve_local_wallet_address", return_value=FROM_ADDRESS),
            patch.object(runtime, "_cast_balance", return_value=balance),
            patch.object(runtime, "_run_cast", return_value=TX_HASH) as run_cast,
            patch.object(runtime, "_wait_for_receipt", return_value=None),
            patch.object(runtime, "_rpc_request") as rpc_request,
        ):
            result = runtime.send_sbc(TO_ADDRESS, "1")

        send_args = run_cast.call_args.args[0]
        self.assertNotIn("--gas-limit", send_args)
        self.assertNotIn("--gas-price", send_args)
        self.assertNotIn("--private-key", send_args)
        self.assertIn("--account", send_args)
        self.assertEqual(result["tx_hash"], TX_HASH)
        rpc_request.assert_not_called()

    def test_send_sbc_mainnet_network_override_uses_mainnet_config(self):
        runtime = RadiusWalletRuntime()
        balance = {
            "address": FROM_ADDRESS,
            "rusd": "0",
            "rusd_raw": "0",
            "sbc": "1",
            "sbc_raw": "1000000",
        }
        with (
            patch.object(RadiusWalletRuntime, "_signer_args", return_value=["--account", "radius-dev"]),
            patch.object(RadiusWalletRuntime, "_resolve_local_wallet_address", return_value=FROM_ADDRESS),
            patch.object(RadiusWalletRuntime, "_cast_balance", return_value=balance),
            patch.object(RadiusWalletRuntime, "_run_cast", return_value=TX_HASH) as run_cast,
            patch.object(RadiusWalletRuntime, "_wait_for_receipt", return_value=None),
        ):
            result = runtime.send_sbc(TO_ADDRESS, "1", network="mainnet")

        send_args = run_cast.call_args.args[0]
        self.assertIn("https://rpc.radiustech.xyz", send_args)
        self.assertIn("723487", send_args)
        self.assertEqual(result["network"], "mainnet")
        self.assertEqual(result["explorer_url"], f"https://network.radiustech.xyz/tx/{TX_HASH}")

    def test_tx_status_pending_on_null_receipt(self):
        runtime = RadiusWalletRuntime()
        with patch.object(runtime, "_rpc_request", return_value=None):
            result = runtime.tx_status(TX_HASH)
        self.assertEqual(result["tx_hash"], TX_HASH)
        self.assertEqual(result["status_label"], "pending")
        self.assertEqual(result["network"], "testnet")
        self.assertEqual(result["explorer_url"], f"https://testnet.radiustech.xyz/tx/{TX_HASH}")

    def test_fee_balance_rejects_exact_sbc_para_transfer_without_fee_source(self):
        runtime = RadiusWalletRuntime()
        balance = {
            "address": FROM_ADDRESS,
            "rusd": "0",
            "rusd_raw": "0",
            "sbc": "1",
            "sbc_raw": "1000000",
        }
        fee = GasFeeEstimate(gas_estimate=21_000, gas_limit=21_000, gas_price_wei=1, fee_wei=21_000)
        with self.assertRaisesRegex(RuntimeError, "Turnstile"):
            runtime._ensure_fee_balance(
                balance,
                fee,
                rusd_reserved_wei=0,
                sbc_reserved_raw=1_000_000,
                transfer_description="1 SBC",
            )

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
