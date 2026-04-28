from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_RPC_URL = "https://rpc.testnet.radiustech.xyz"
DEFAULT_CHAIN_ID = "72344"
DEFAULT_SBC_ADDRESS = "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb"
DEFAULT_EXPLORER_URL = "https://testnet.radiustech.xyz"
MAINNET_RPC_URL = "https://rpc.radiustech.xyz"
MAINNET_CHAIN_ID = "723487"
MAINNET_EXPLORER_URL = "https://network.radiustech.xyz"
DEFAULT_PARA_BASE_URL_BETA = "https://api.beta.getpara.com"
DEFAULT_PARA_BASE_URL_PROD = "https://api.getpara.com"
SBC_DECIMALS = 6
RUSD_DECIMALS = 18
MIN_TRANSACTION_GAS = 21_000
SBC_TRANSFER_GAS_EXTRA = 10_000
SBC_TRANSFER_GAS_NUMERATOR = 6
SBC_TRANSFER_GAS_DENOMINATOR = 5
RUSD_TRANSFER_GAS_EXTRA = 1_000
RUSD_TRANSFER_GAS_NUMERATOR = 11
RUSD_TRANSFER_GAS_DENOMINATOR = 10
TURNSTILE_MIN_SBC_RAW = 100_000
TURNSTILE_MAX_SBC_RAW = 10_000_000
RUSD_WEI_PER_SBC_RAW = 10 ** (RUSD_DECIMALS - SBC_DECIMALS)
VALID_PROVIDERS = {"local", "para"}
VALID_NETWORKS = {"testnet", "mainnet"}
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TX_HASH_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
DECIMAL_AMOUNT_RE = re.compile(r"^(?:\d+(?:\.\d*)?|\.\d+)$")


@dataclass(frozen=True)
class RadiusNetworkConfig:
    rpc_url: str
    chain_id: str
    sbc_address: str
    explorer_url: str

    @property
    def chain_id_int(self) -> int:
        return int(self.chain_id)

    @property
    def network(self) -> str:
        if self.chain_id == "72344":
            return "testnet"
        if self.chain_id == "723487":
            return "mainnet"
        return "custom"


@dataclass(frozen=True)
class GasFeeEstimate:
    gas_estimate: int
    gas_limit: int
    gas_price_wei: int
    fee_wei: int


def _format_units(value: int, decimals: int) -> str:
    negative = value < 0
    if negative:
        value = -value
    s = str(value).zfill(decimals)
    integer = s[:-decimals] if len(s) > decimals else "0"
    fraction = s[len(s) - decimals :].rstrip("0")
    sign = "-" if negative else ""
    return f"{sign}{integer}{f'.{fraction}' if fraction else ''}"


def _parse_units(amount_str: str, decimals: int) -> int:
    if decimals < 0:
        raise ValueError("decimals must be non-negative")
    text = str(amount_str or "").strip()
    if not text:
        raise ValueError("missing amount")
    if not DECIMAL_AMOUNT_RE.fullmatch(text):
        raise ValueError(f"invalid decimal amount: {amount_str!r}")

    integer_part, separator, fraction_part = text.partition(".")
    integer_part = integer_part or "0"
    if int(integer_part) == 0 and not any(digit != "0" for digit in fraction_part):
        raise ValueError("amount must be greater than zero")

    if len(fraction_part) > decimals:
        supported_fraction = fraction_part[:decimals].ljust(decimals, "0")
        if int(integer_part) == 0 and int(supported_fraction or "0") == 0:
            raise ValueError(f"amount is below the smallest base unit ({decimals} decimals)")
        raise ValueError(f"amount has too many decimal places for {decimals}-decimal asset")

    scale = 10**decimals
    fraction_raw = int(fraction_part.ljust(decimals, "0") or "0") if separator else 0
    raw_amount = int(integer_part) * scale + fraction_raw
    if raw_amount == 0:
        raise ValueError(f"amount is below the smallest base unit ({decimals} decimals)")
    return raw_amount


def _gas_limit_with_buffer(
    gas_estimate: int,
    extra_gas: int,
    numerator: int,
    denominator: int,
) -> int:
    if gas_estimate <= 0:
        raise ValueError(f"invalid gas estimate: {gas_estimate}")
    percent_buffer = (gas_estimate * numerator + denominator - 1) // denominator
    return max(gas_estimate + extra_gas, percent_buffer)


def _fee_from_gas_estimate(
    gas_estimate: int,
    gas_price_wei: int,
    extra_gas: int,
    numerator: int,
    denominator: int,
) -> GasFeeEstimate:
    if gas_price_wei <= 0:
        raise ValueError(f"invalid gas price: {gas_price_wei}")
    gas_limit = _gas_limit_with_buffer(gas_estimate, extra_gas, numerator, denominator)
    return GasFeeEstimate(
        gas_estimate=gas_estimate,
        gas_limit=gas_limit,
        gas_price_wei=gas_price_wei,
        fee_wei=gas_limit * gas_price_wei,
    )


def _minimum_fee_estimate(gas_price_wei: int) -> GasFeeEstimate:
    return GasFeeEstimate(
        gas_estimate=MIN_TRANSACTION_GAS,
        gas_limit=MIN_TRANSACTION_GAS,
        gas_price_wei=gas_price_wei,
        fee_wei=MIN_TRANSACTION_GAS * gas_price_wei,
    )


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _rusd_wei_to_sbc_raw_ceil(value_wei: int) -> int:
    return _ceil_div(value_wei, RUSD_WEI_PER_SBC_RAW)


def _normalize_provider(provider: str | None) -> str:
    value = str(provider or "local").strip().lower()
    if value not in VALID_PROVIDERS:
        raise ValueError(
            f"invalid provider {provider!r}; expected one of: {', '.join(sorted(VALID_PROVIDERS))}"
        )
    return value


def _normalize_network(network: str | None) -> str | None:
    if network is None:
        return None
    value = str(network or "").strip().lower()
    if not value:
        return None
    if value not in VALID_NETWORKS:
        raise ValueError(
            f"invalid network {network!r}; expected one of: {', '.join(sorted(VALID_NETWORKS))}"
        )
    return value


def _network_config_from_env() -> RadiusNetworkConfig:
    return RadiusNetworkConfig(
        rpc_url=str(os.environ.get("RADIUS_RPC_URL") or DEFAULT_RPC_URL).strip(),
        chain_id=str(os.environ.get("RADIUS_CHAIN_ID") or DEFAULT_CHAIN_ID).strip(),
        sbc_address=str(os.environ.get("RADIUS_SBC_ADDRESS") or DEFAULT_SBC_ADDRESS).strip(),
        explorer_url=str(os.environ.get("RADIUS_EXPLORER_URL") or DEFAULT_EXPLORER_URL).strip().rstrip("/"),
    )


def _network_config_for_name(network: str | None) -> RadiusNetworkConfig | None:
    value = _normalize_network(network)
    if value is None:
        return None
    if value == "testnet":
        return RadiusNetworkConfig(
            rpc_url=DEFAULT_RPC_URL,
            chain_id=DEFAULT_CHAIN_ID,
            sbc_address=DEFAULT_SBC_ADDRESS,
            explorer_url=DEFAULT_EXPLORER_URL,
        )
    return RadiusNetworkConfig(
        rpc_url=MAINNET_RPC_URL,
        chain_id=MAINNET_CHAIN_ID,
        sbc_address=DEFAULT_SBC_ADDRESS,
        explorer_url=MAINNET_EXPLORER_URL,
    )


def _validate_address(address: str) -> str:
    text = str(address or "").strip()
    if not ADDRESS_RE.fullmatch(text):
        raise ValueError(f"invalid EVM address: {address!r}")
    return text


def _validate_tx_hash(tx_hash: str) -> str:
    text = str(tx_hash or "").strip()
    if not TX_HASH_RE.fullmatch(text):
        raise ValueError(f"invalid transaction hash: {tx_hash!r}")
    return text


def _parse_int(output: str) -> int:
    value = str(output or "").strip()
    if not value:
        raise ValueError("expected integer output, got empty string")

    first_token = value.split()[0]
    if first_token.startswith("0x"):
        return int(first_token, 16)

    match = re.match(r"^[+-]?\d+", first_token)
    if match:
        return int(match.group(0))

    raise ValueError(f"could not parse integer from output: {output!r}")


def _status_label(status) -> str:
    if status in (1, "1", "0x1", True):
        return "success"
    if status in (0, "0", "0x0", False):
        return "reverted"
    return "unknown"


def _radius_state_dir() -> Path:
    explicit = str(os.environ.get("RADIUS_STATE_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    hermes_home = str(os.environ.get("HERMES_HOME") or "").strip()
    if hermes_home:
        return Path(hermes_home).expanduser() / ".radius"
    return Path.home() / ".radius"


def _private_key_file() -> Path:
    return _radius_state_dir() / "key"


def _address_file() -> Path:
    return _radius_state_dir() / "address"


class RadiusWalletRuntime:
    def __init__(self, config: RadiusNetworkConfig | None = None) -> None:
        self.config = config or _network_config_from_env()
        self._para_wallet_cache: dict[str, object] = {"value": None, "expires_at": 0.0}

    def for_network(self, network: str | None) -> "RadiusWalletRuntime":
        config = _network_config_for_name(network)
        if config is None or config == self.config:
            return self
        return RadiusWalletRuntime(config=config)

    def wallet_address(self, provider: str = "local") -> dict:
        provider = _normalize_provider(provider)
        if provider == "para":
            return self._para_wallet_address()
        return {
            "address": self._resolve_local_wallet_address(),
            "provider": "local",
            "backend": "cast",
            "network": self.config.network,
        }

    def balance(self, provider: str = "local", address: str | None = None) -> dict:
        provider = _normalize_provider(provider)
        if address:
            address = _validate_address(address)
        if provider == "para":
            target = address or str(self._resolve_para_wallet()["address"])
            data = self._cast_balance(target)
            data["provider"] = "para"
            data["backend"] = "para-rest"
            data["network"] = self.config.network
            return data

        target = address or self._resolve_local_wallet_address()
        data = self._cast_balance(target)
        data["provider"] = "local"
        data["backend"] = "cast"
        data["network"] = self.config.network
        return data

    def send_sbc(
        self,
        to_address: str,
        amount_sbc: str,
        provider: str = "local",
        network: str | None = None,
    ) -> dict:
        runtime = self.for_network(network)
        if runtime is not self:
            return runtime.send_sbc(to_address, amount_sbc, provider=provider)
        provider = _normalize_provider(provider)
        to_address = _validate_address(to_address)
        amount_raw = _parse_units(amount_sbc, SBC_DECIMALS)
        if provider == "para":
            return self._send_sbc_para(to_address, amount_sbc, amount_raw)
        return self._send_sbc_local(to_address, amount_sbc, amount_raw)

    def send_rusd(
        self,
        to_address: str,
        amount_rusd: str,
        provider: str = "local",
        network: str | None = None,
    ) -> dict:
        runtime = self.for_network(network)
        if runtime is not self:
            return runtime.send_rusd(to_address, amount_rusd, provider=provider)
        provider = _normalize_provider(provider)
        to_address = _validate_address(to_address)
        value_wei = _parse_units(amount_rusd, RUSD_DECIMALS)
        if provider == "para":
            return self._send_rusd_para(to_address, amount_rusd, value_wei)
        return self._send_rusd_local(to_address, amount_rusd, value_wei)

    def tx_status(self, tx_hash: str) -> dict:
        tx_hash = _validate_tx_hash(tx_hash)
        receipt = self._rpc_request("eth_getTransactionReceipt", [tx_hash])
        if receipt is None:
            return {
                "tx_hash": tx_hash,
                "status": None,
                "status_label": "pending",
                "explorer_url": f"{self.config.explorer_url}/tx/{tx_hash}",
                "backend": "rpc",
                "network": self.config.network,
            }
        if not isinstance(receipt, dict) or not receipt:
            raise RuntimeError(f"unexpected transaction receipt payload for {tx_hash}: {receipt!r}")
        status = receipt.get("status")
        return {
            "tx_hash": tx_hash,
            "status": status,
            "status_label": _status_label(status),
            "block_number": str(
                self._rpc_field_to_string(receipt.get("blockNumber"))
                or receipt.get("block_number")
                or receipt.get("block")
                or ""
            ),
            "explorer_url": f"{self.config.explorer_url}/tx/{tx_hash}",
            "backend": "rpc",
            "network": self.config.network,
            "raw": receipt,
        }

    def chain_info(self) -> dict:
        result = {
            "network": self.config.network,
            "rpc_url": self.config.rpc_url,
            "chain_id": self.config.chain_id,
            "explorer_url": self.config.explorer_url,
            "sbc_address": self.config.sbc_address,
            "sbc_decimals": SBC_DECIMALS,
            "rusd_decimals": RUSD_DECIMALS,
            "gas_mode": "fixed-no-eip1559",
            "block_number_semantics": "timestamp-ms",
            "finality": "sub-second",
        }
        try:
            result["gas_price_wei"] = str(_parse_int(str(self._rpc_request("eth_gasPrice", []))))
        except Exception as err:
            result["gas_price_error"] = str(err)
        try:
            result["block_number"] = self._rpc_field_to_string(
                self._rpc_request("eth_blockNumber", [])
            )
        except Exception as err:
            result["block_number_error"] = str(err)
        return result

    def _rpc_request(self, method: str, params: list) -> object:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.config.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Radius RPC HTTP error: {err.code} {body}") from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"Radius RPC connection error: {err.reason}") from err

        if data.get("error"):
            message = data["error"].get("message") or json.dumps(data["error"])
            raise RuntimeError(f"Radius RPC error: {message}")
        return data.get("result")

    def _rpc_field_to_string(self, value: object) -> str:
        if isinstance(value, str) and value.startswith("0x"):
            return str(int(value, 16))
        return str(value or "")

    def _run_command(self, cmd: list[str], env: dict[str, str] | None = None) -> str:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            message = stderr or stdout or f"command failed with exit code {result.returncode}"
            raise RuntimeError(message)
        return (result.stdout or "").strip()

    def _cast_env(self) -> dict[str, str]:
        env = os.environ.copy()
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            env.pop(key, None)
        env.setdefault("NO_PROXY", "*")
        env.setdefault("no_proxy", "*")
        return env

    def _cast_bin(self) -> str:
        explicit = str(os.environ.get("RADIUS_CAST_BIN") or "").strip()
        if explicit:
            return explicit
        on_path = shutil.which("cast")
        if on_path:
            return on_path
        for candidate in (
            "/root/.foundry/bin/cast",
            "/usr/local/bin/cast",
            "/opt/foundry/bin/cast",
        ):
            if Path(candidate).exists():
                return candidate
        raise RuntimeError(
            "Foundry cast is not installed or not on PATH. Set RADIUS_CAST_BIN or install Foundry."
        )

    def _run_cast(self, args: list[str]) -> str:
        return self._run_command([self._cast_bin(), *args], env=self._cast_env())

    def _signer_args(self) -> list[str]:
        account = str(os.environ.get("RADIUS_ACCOUNT") or "").strip()
        if account:
            args = ["--account", account]
            keystore = str(os.environ.get("RADIUS_KEYSTORE") or "").strip()
            if keystore:
                args.extend(["--keystore", keystore])
            password_file = str(os.environ.get("RADIUS_PASSWORD_FILE") or "").strip()
            if password_file:
                args.extend(["--password-file", password_file])
            return args

        if str(os.environ.get("RADIUS_PRIVATE_KEY") or "").strip():
            raise RuntimeError(
                "RADIUS_PRIVATE_KEY is intentionally not passed to cast command lines because it "
                "can leak via process listings. Import it once with `cast wallet import` and set "
                "RADIUS_ACCOUNT instead."
            )

        key_file = _private_key_file()
        if key_file.exists():
            raise RuntimeError(
                f"Private key file {key_file} is intentionally not passed to cast command lines. "
                "Import it once with `cast wallet import` and set RADIUS_ACCOUNT instead."
            )

        raise RuntimeError(
            "No wallet signer configured. Set RADIUS_ACCOUNT to a Foundry keystore account "
            "created with `cast wallet import`."
        )

    def _read_address_hint(self) -> str:
        address = str(os.environ.get("RADIUS_WALLET_ADDRESS") or "").strip()
        if address:
            return address
        address_file = _address_file()
        if address_file.exists():
            return address_file.read_text(encoding="utf-8").strip()
        return ""

    def _resolve_local_wallet_address(self) -> str:
        address = self._read_address_hint()
        if address:
            return _validate_address(address)
        return _validate_address(
            self._run_cast(["wallet", "address", *self._signer_args()]).strip()
        )

    def _cast_balance(self, address: str) -> dict:
        rusd_raw = _parse_int(
            self._run_cast(["balance", address, "--rpc-url", self.config.rpc_url])
        )
        sbc_raw = _parse_int(
            self._run_cast(
                [
                    "call",
                    self.config.sbc_address,
                    "balanceOf(address)(uint256)",
                    address,
                    "--rpc-url",
                    self.config.rpc_url,
                ]
            )
        )
        return {
            "address": address,
            "rusd": _format_units(rusd_raw, RUSD_DECIMALS),
            "rusd_raw": str(rusd_raw),
            "sbc": _format_units(sbc_raw, SBC_DECIMALS),
            "sbc_raw": str(sbc_raw),
        }

    def _gas_metadata(self, fee: GasFeeEstimate) -> dict:
        return {
            "gas_estimate": str(fee.gas_estimate),
            "gas_limit": str(fee.gas_limit),
            "gas_price_wei": str(fee.gas_price_wei),
            "estimated_gas_fee_wei": str(fee.fee_wei),
            "estimated_gas_fee_rusd": _format_units(fee.fee_wei, RUSD_DECIMALS),
        }

    def _ensure_fee_balance(
        self,
        balance: dict,
        fee: GasFeeEstimate,
        *,
        rusd_reserved_wei: int,
        sbc_reserved_raw: int,
        transfer_description: str,
        fee_label: str = "estimated gas fee",
    ) -> None:
        rusd_available_wei = int(balance["rusd_raw"]) - rusd_reserved_wei
        sbc_available_raw = int(balance["sbc_raw"]) - sbc_reserved_raw
        if rusd_available_wei >= fee.fee_wei:
            return

        fee_deficit_wei = fee.fee_wei - max(rusd_available_wei, 0)
        turnstile_required_sbc_raw = max(
            _rusd_wei_to_sbc_raw_ceil(fee_deficit_wei),
            TURNSTILE_MIN_SBC_RAW,
        )
        if turnstile_required_sbc_raw > TURNSTILE_MAX_SBC_RAW:
            raise RuntimeError(
                f"Insufficient balance for {fee_label}. "
                f"Need {_format_units(fee.fee_wei, RUSD_DECIMALS)} RUSD for gas, "
                f"which exceeds the Turnstile per-transaction conversion limit."
            )

        if sbc_available_raw >= turnstile_required_sbc_raw:
            return

        raise RuntimeError(
            f"Insufficient balance for {fee_label}. "
            f"Need {_format_units(fee.fee_wei, RUSD_DECIMALS)} RUSD for gas after "
            f"sending {transfer_description}. Available for fees: "
            f"{_format_units(max(rusd_available_wei, 0), RUSD_DECIMALS)} RUSD and "
            f"{_format_units(max(sbc_available_raw, 0), SBC_DECIMALS)} SBC. "
            f"Need enough RUSD for gas or at least "
            f"{_format_units(turnstile_required_sbc_raw, SBC_DECIMALS)} SBC "
            f"available for Turnstile."
        )

    def _wait_for_receipt(self, tx_hash: str) -> dict | None:
        try:
            receipt_raw = self._run_cast(
                [
                    "receipt",
                    tx_hash,
                    "--rpc-url",
                    self.config.rpc_url,
                    "--confirmations",
                    "1",
                    "--json",
                ]
            )
        except Exception:
            return None
        try:
            return json.loads(receipt_raw)
        except json.JSONDecodeError:
            return None

    def _apply_receipt(self, result: dict, receipt: dict | None) -> dict:
        if receipt is None:
            return result
        status = receipt.get("status")
        result["status"] = _status_label(status)
        result["receipt_status"] = status
        result["block_number"] = str(
            self._rpc_field_to_string(receipt.get("blockNumber"))
            or receipt.get("block_number")
            or receipt.get("block")
            or ""
        )
        result["receipt"] = receipt
        return result

    def _send_sbc_local(self, to_address: str, amount_sbc: str, amount_raw: int) -> dict:
        signer_args = self._signer_args()
        from_address = self._resolve_local_wallet_address()
        balance = self._cast_balance(from_address)
        if int(balance["sbc_raw"]) < amount_raw:
            raise RuntimeError(
                f"Insufficient SBC balance. Have {balance['sbc']}, need {amount_sbc}."
            )

        tx_hash = self._run_cast(
            [
                "send",
                self.config.sbc_address,
                "transfer(address,uint256)",
                to_address,
                str(amount_raw),
                "--rpc-url",
                self.config.rpc_url,
                *signer_args,
                "--chain",
                self.config.chain_id,
                "--legacy",
                "--async",
            ]
        ).strip()
        result = {
            "from": from_address,
            "to": to_address,
            "asset": "SBC",
            "amount_sbc": amount_sbc,
            "amount_raw": str(amount_raw),
            "tx_hash": tx_hash,
            "status": "submitted",
            "provider": "local",
            "backend": "cast",
            "network": self.config.network,
            "explorer_url": f"{self.config.explorer_url}/tx/{tx_hash}",
        }
        return self._apply_receipt(result, self._wait_for_receipt(tx_hash))

    def _send_rusd_local(self, to_address: str, amount_rusd: str, value_wei: int) -> dict:
        signer_args = self._signer_args()
        from_address = self._resolve_local_wallet_address()
        balance = self._cast_balance(from_address)
        if int(balance["rusd_raw"]) < value_wei:
            raise RuntimeError(
                f"Insufficient RUSD balance. Have {balance['rusd']}, need {amount_rusd}."
            )

        tx_hash = self._run_cast(
            [
                "send",
                to_address,
                "--value",
                str(value_wei),
                "--rpc-url",
                self.config.rpc_url,
                *signer_args,
                "--chain",
                self.config.chain_id,
                "--legacy",
                "--async",
            ]
        ).strip()
        result = {
            "from": from_address,
            "to": to_address,
            "asset": "RUSD",
            "amount_rusd": amount_rusd,
            "value_wei": str(value_wei),
            "tx_hash": tx_hash,
            "status": "submitted",
            "provider": "local",
            "backend": "cast",
            "network": self.config.network,
            "explorer_url": f"{self.config.explorer_url}/tx/{tx_hash}",
        }
        return self._apply_receipt(result, self._wait_for_receipt(tx_hash))

    def _para_base_url(self) -> str:
        explicit = str(os.environ.get("PARA_REST_BASE_URL") or "").strip()
        if explicit:
            return explicit.rstrip("/")
        env = str(os.environ.get("PARA_ENVIRONMENT") or "beta").strip().lower()
        if env in {"prod", "production"}:
            return DEFAULT_PARA_BASE_URL_PROD
        return DEFAULT_PARA_BASE_URL_BETA

    def _para_api_key(self) -> str:
        for key in ("PARA_API_KEY", "PARA_SECRET_API_KEY"):
            value = str(os.environ.get(key) or "").strip()
            if value:
                return value
        raise RuntimeError("Para wallet provider unavailable: set PARA_API_KEY for Para REST access")

    def _para_headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self._para_api_key(),
            "Content-Type": "application/json",
        }

    def _para_request(self, method: str, path: str, payload: dict | None = None):
        import requests

        url = f"{self._para_base_url()}{path}"
        response = requests.request(
            method,
            url,
            headers=self._para_headers(),
            json=payload,
            timeout=30,
        )
        try:
            data = response.json()
        except Exception:
            data = None
        if not response.ok:
            message = None
            if isinstance(data, dict):
                message = data.get("message") or data.get("code")
            raise RuntimeError(
                f"Para wallet provider unavailable: {message or f'{response.status_code} {response.text.strip()}'}"
            )
        return data if data is not None else {}

    def _coerce_wallet_list(self, data) -> list[dict]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("wallets", "items", "data", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _wallet_type(self, wallet: dict) -> str:
        return str(wallet.get("type") or wallet.get("walletType") or "").strip().lower()

    def _wallet_id(self, wallet: dict) -> str:
        return str(wallet.get("id") or wallet.get("walletId") or "").strip()

    def _wallet_address(self, wallet: dict) -> str:
        for key in ("address", "walletAddress", "publicAddress"):
            value = str(wallet.get(key) or "").strip()
            if value:
                return value
        return ""

    def _cached_para_wallet(self) -> dict | None:
        value = self._para_wallet_cache.get("value")
        expires_at = float(self._para_wallet_cache.get("expires_at") or 0.0)
        if value and time.time() < expires_at:
            return value if isinstance(value, dict) else None
        return None

    def _store_para_wallet(self, wallet: dict) -> dict:
        self._para_wallet_cache["value"] = wallet
        self._para_wallet_cache["expires_at"] = time.time() + 30.0
        return wallet

    def _resolve_para_wallet(self) -> dict:
        cached = self._cached_para_wallet()
        if cached:
            return cached

        explicit_wallet_id = str(os.environ.get("PARA_WALLET_ID") or "").strip()
        if explicit_wallet_id:
            wallet = self._para_request("GET", f"/v1/wallets/{explicit_wallet_id}")
            if not isinstance(wallet, dict):
                raise RuntimeError("Para wallet provider unavailable: unexpected wallet payload")
            wallet_id = self._wallet_id(wallet)
            address = self._wallet_address(wallet)
            if not wallet_id or not address:
                raise RuntimeError("Para wallet provider unavailable: wallet payload missing id or address")
            return self._store_para_wallet(
                {"id": wallet_id, "address": address, "type": self._wallet_type(wallet)}
            )

        wallets = self._coerce_wallet_list(self._para_request("GET", "/v1/wallets"))
        evm_wallets = [wallet for wallet in wallets if self._wallet_type(wallet) == "evm"]
        if not evm_wallets:
            raise RuntimeError("Para wallet provider unavailable: no EVM wallet found")
        if len(evm_wallets) > 1:
            raise RuntimeError(
                "Para wallet provider unavailable: multiple EVM wallets found; set PARA_WALLET_ID"
            )

        wallet = evm_wallets[0]
        wallet_id = self._wallet_id(wallet)
        address = self._wallet_address(wallet)
        if not wallet_id or not address:
            raise RuntimeError("Para wallet provider unavailable: wallet payload missing id or address")
        return self._store_para_wallet(
            {"id": wallet_id, "address": address, "type": self._wallet_type(wallet)}
        )

    def _ensure_hex_prefixed(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeError("Para wallet provider unavailable: missing signed transaction payload")
        return text if text.startswith("0x") else f"0x{text}"

    def _extract_signed_transaction(self, payload) -> str:
        if isinstance(payload, dict):
            for key in ("transactionData", "signedTransaction", "signature", "data"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return self._ensure_hex_prefixed(value)
            inner = payload.get("result")
            if isinstance(inner, dict):
                return self._extract_signed_transaction(inner)
        raise RuntimeError(
            "Para wallet provider unavailable: sign-transaction response did not include a signed transaction"
        )

    def _broadcast_raw_transaction(self, raw_tx: str) -> str:
        import requests

        response = requests.post(
            self.config.rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_sendRawTransaction",
                "params": [raw_tx],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            message = data["error"].get("message") or json.dumps(data["error"])
            raise RuntimeError(f"Radius RPC broadcast failed: {message}")
        tx_hash = str(data.get("result") or "").strip()
        if not tx_hash:
            raise RuntimeError("Radius RPC broadcast did not return a transaction hash")
        return tx_hash

    def _create_web3(self):
        from web3 import Web3

        return Web3(Web3.HTTPProvider(self.config.rpc_url))

    def _erc20_contract(self, w3):
        from web3 import Web3

        return w3.eth.contract(
            address=Web3.to_checksum_address(self.config.sbc_address),
            abi=[
                {
                    "type": "function",
                    "name": "transfer",
                    "inputs": [
                        {"name": "to", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                    ],
                    "outputs": [{"name": "", "type": "bool"}],
                    "stateMutability": "nonpayable",
                }
            ],
        )

    def _para_wallet_address(self) -> dict:
        wallet = self._resolve_para_wallet()
        return {
            "address": wallet["address"],
            "wallet_id": wallet["id"],
            "provider": "para",
            "backend": "para-rest",
            "network": self.config.network,
        }

    def _send_sbc_para(self, to_address: str, amount_sbc: str, amount_raw: int) -> dict:
        from web3 import Web3
        from web3.exceptions import ContractLogicError

        wallet = self._resolve_para_wallet()
        from_address = str(wallet["address"])
        wallet_id = str(wallet["id"])
        balance = self.balance(provider="para", address=from_address)
        if int(balance["sbc_raw"]) < amount_raw:
            raise RuntimeError(
                f"Insufficient SBC balance. Have {balance['sbc']}, need {amount_sbc}."
            )

        w3 = self._create_web3()
        contract = self._erc20_contract(w3)
        checksum_from = Web3.to_checksum_address(from_address)
        checksum_to = Web3.to_checksum_address(to_address)
        tx_data = contract.functions.transfer(checksum_to, amount_raw)._encode_transaction_data()
        gas_price = int(w3.eth.gas_price)
        self._ensure_fee_balance(
            balance,
            _minimum_fee_estimate(gas_price),
            rusd_reserved_wei=0,
            sbc_reserved_raw=amount_raw,
            transfer_description=f"{amount_sbc} SBC",
            fee_label="minimum gas fee",
        )
        nonce = int(w3.eth.get_transaction_count(checksum_from))
        try:
            gas_estimate = int(
                w3.eth.estimate_gas(
                    {
                        "from": checksum_from,
                        "to": Web3.to_checksum_address(self.config.sbc_address),
                        "data": tx_data,
                        "value": 0,
                    }
                )
            )
        except ContractLogicError as err:
            message = str(err)
            if "transfer amount exceeds balance" in message.lower():
                raise RuntimeError(
                    f"Insufficient SBC balance. Have {balance['sbc']}, need {amount_sbc}."
                ) from err
            raise
        fee = _fee_from_gas_estimate(
            gas_estimate,
            gas_price,
            SBC_TRANSFER_GAS_EXTRA,
            SBC_TRANSFER_GAS_NUMERATOR,
            SBC_TRANSFER_GAS_DENOMINATOR,
        )
        self._ensure_fee_balance(
            balance,
            fee,
            rusd_reserved_wei=0,
            sbc_reserved_raw=amount_raw,
            transfer_description=f"{amount_sbc} SBC",
        )

        sign_payload = {
            "transaction": {
                "to": Web3.to_checksum_address(self.config.sbc_address),
                "value": 0,
                "gasLimit": fee.gas_limit,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.config.chain_id_int,
                "data": tx_data,
                "type": 0,
            },
            "chainId": self.config.chain_id_int,
        }
        signed = self._extract_signed_transaction(
            self._para_request("POST", f"/v1/wallets/{wallet_id}/sign-transaction", sign_payload)
        )
        tx_hash = self._broadcast_raw_transaction(signed)
        result = {
            "from": from_address,
            "to": to_address,
            "asset": "SBC",
            "amount_sbc": amount_sbc,
            "amount_raw": str(amount_raw),
            "tx_hash": tx_hash,
            "status": "submitted",
            "provider": "para",
            "backend": "para-rest",
            "wallet_id": wallet_id,
            "network": self.config.network,
            "explorer_url": f"{self.config.explorer_url}/tx/{tx_hash}",
        }
        result.update(self._gas_metadata(fee))
        return self._apply_receipt(result, self._wait_for_receipt(tx_hash))

    def _send_rusd_para(self, to_address: str, amount_rusd: str, value_wei: int) -> dict:
        from web3 import Web3

        wallet = self._resolve_para_wallet()
        from_address = str(wallet["address"])
        wallet_id = str(wallet["id"])
        balance = self.balance(provider="para", address=from_address)
        if int(balance["rusd_raw"]) < value_wei:
            raise RuntimeError(
                f"Insufficient RUSD balance. Have {balance['rusd']}, need {amount_rusd}."
            )

        w3 = self._create_web3()
        checksum_from = Web3.to_checksum_address(from_address)
        checksum_to = Web3.to_checksum_address(to_address)
        gas_price = int(w3.eth.gas_price)
        self._ensure_fee_balance(
            balance,
            _minimum_fee_estimate(gas_price),
            rusd_reserved_wei=value_wei,
            sbc_reserved_raw=0,
            transfer_description=f"{amount_rusd} RUSD",
            fee_label="minimum gas fee",
        )
        nonce = int(w3.eth.get_transaction_count(checksum_from))
        gas_estimate = int(
            w3.eth.estimate_gas(
                {
                    "from": checksum_from,
                    "to": checksum_to,
                    "value": value_wei,
                    "data": "0x",
                }
            )
        )
        fee = _fee_from_gas_estimate(
            gas_estimate,
            gas_price,
            RUSD_TRANSFER_GAS_EXTRA,
            RUSD_TRANSFER_GAS_NUMERATOR,
            RUSD_TRANSFER_GAS_DENOMINATOR,
        )
        self._ensure_fee_balance(
            balance,
            fee,
            rusd_reserved_wei=value_wei,
            sbc_reserved_raw=0,
            transfer_description=f"{amount_rusd} RUSD",
        )
        sign_payload = {
            "transaction": {
                "to": checksum_to,
                "value": value_wei,
                "gasLimit": fee.gas_limit,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": self.config.chain_id_int,
                "data": "0x",
                "type": 0,
            },
            "chainId": self.config.chain_id_int,
        }
        signed = self._extract_signed_transaction(
            self._para_request("POST", f"/v1/wallets/{wallet_id}/sign-transaction", sign_payload)
        )
        tx_hash = self._broadcast_raw_transaction(signed)
        result = {
            "from": from_address,
            "to": to_address,
            "asset": "RUSD",
            "amount_rusd": amount_rusd,
            "value_wei": str(value_wei),
            "tx_hash": tx_hash,
            "status": "submitted",
            "provider": "para",
            "backend": "para-rest",
            "wallet_id": wallet_id,
            "network": self.config.network,
            "explorer_url": f"{self.config.explorer_url}/tx/{tx_hash}",
        }
        result.update(self._gas_metadata(fee))
        return self._apply_receipt(result, self._wait_for_receipt(tx_hash))
