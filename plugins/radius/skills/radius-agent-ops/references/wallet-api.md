# Wallet API Reference

Complete API reference for `radius-wallet-py` (Python) and `radius-wallet-ts` (TypeScript). Both libraries provide identical functionality with language-idiomatic interfaces.

## Installation

**Python:**

```bash
pip install git+https://github.com/radiustechsystems/radius-wallet-py.git
```

Dependencies: `eth-account`, `httpx`, `eth-abi`, `eth-utils`. Single-file library — can also vendor `radius_wallet.py` directly into a project.

**TypeScript:**

```bash
npm install github:radiustechsystems/radius-wallet-ts
```

Dependency: `viem`. Two source files (`wallet.ts`, `constants.ts`) — can also copy into a project.

## Wallet Construction

### Constructor

**Python:**
```python
from radius_wallet import RadiusWallet

wallet = RadiusWallet(
    private_key="0x...",            # Required. 0x-prefixed hex string.
    rpc_url=TESTNET_RPC,            # Optional. Defaults to testnet.
    chain_id=TESTNET_CHAIN_ID,      # Optional. Defaults to 72344.
)
```

**TypeScript:**
```typescript
import { RadiusWallet } from "radius-wallet-ts";

const wallet = new RadiusWallet(
  "0x...",                          // Required. 0x-prefixed hex string.
  { chain: "testnet" }              // Optional. "testnet" (default) or "mainnet".
);
```

### Factory Methods

| Method | Python | TypeScript |
|--------|--------|------------|
| Generate new random wallet | `RadiusWallet.create()` | `RadiusWallet.create()` |
| Load from env var | `RadiusWallet.from_env()` | `RadiusWallet.fromEnv()` |

Both accept the same network configuration options as the constructor.

**Mainnet configuration:**

```python
# Python
from radius_wallet import RadiusWallet, MAINNET_RPC, MAINNET_CHAIN_ID
wallet = RadiusWallet("0x...", rpc_url=MAINNET_RPC, chain_id=MAINNET_CHAIN_ID)
```

```typescript
// TypeScript
const wallet = new RadiusWallet("0x...", { chain: "mainnet" });
```

### Properties

| Property | Python | TypeScript | Returns |
|----------|--------|------------|---------|
| Public address | `wallet.address` | `wallet.address` | `str` / `Address` |
| Chain definition | *(no equivalent)* | `wallet.chain` | `Chain` (viem) |

## Balance Methods

### get_rusd_balance / getRusdBalance

Query the native RUSD balance in human-readable units.

| | Python | TypeScript |
|-|--------|------------|
| Signature | `get_rusd_balance(address=None) -> float` | `getRusdBalance(address?) -> Promise<string>` |
| Default | Own wallet address | Own wallet address |
| Returns | `float` (e.g. `1.5`) | `string` (e.g. `"1.5"`) |

### get_sbc_balance / getSbcBalance

Query the SBC ERC-20 balance in human-readable units.

| | Python | TypeScript |
|-|--------|------------|
| Signature | `get_sbc_balance(address=None) -> float` | `getSbcBalance(address?) -> Promise<string>` |
| Returns | `float` (e.g. `10.0`) | `string` (e.g. `"10.0"`) |

### get_balances / getBalances

Query both balances in one call.

**Python:**
```python
balances = wallet.get_balances()  # or wallet.get_balances("0xOtherAddress")
# {"address": "0x...", "rusd": 0.001, "sbc": 10.5}
```

**TypeScript:**
```typescript
const balances = await wallet.getBalances();
// { address: "0x...", rusd: "0.001", sbc: "10.5" }
```

## Transfer Methods

### send_sbc / sendSbc

Transfer SBC (ERC-20) to an address. Amount in human-readable units — the library handles 6-decimal conversion.

**Python:**
```python
tx_hash = wallet.send_sbc("0xRecipient", 1.5)  # Sends 1.5 SBC
```

**TypeScript:**
```typescript
const txHash = await wallet.sendSbc("0xRecipient", "1.5");
```

### send_rusd / sendRusd

Transfer RUSD (native token) to an address. Amount in human-readable units — the library handles 18-decimal conversion.

**Python:**
```python
tx_hash = wallet.send_rusd("0xRecipient", 0.001)
```

**TypeScript:**
```typescript
const txHash = await wallet.sendRusd("0xRecipient", "0.001");
```

**Note:** Both methods return the transaction hash as a hex string. Always call `wait_for_tx` / `waitForTx` afterwards to confirm.

## Transaction Status

### get_tx_receipt / getTxReceipt

Fetch a transaction receipt. Python returns `None` if pending; TypeScript throws if pending.

| | Python | TypeScript |
|-|--------|------------|
| Signature | `get_tx_receipt(tx_hash) -> dict or None` | `getTxReceipt(hash) -> Promise<TransactionReceipt>` |

### wait_for_tx / waitForTx

Block until a transaction is confirmed. Returns the receipt.

**Python:**
```python
receipt = wallet.wait_for_tx(tx_hash, timeout=30.0)  # timeout in seconds
```

**TypeScript:**
```typescript
const receipt = await wallet.waitForTx(txHash);
```

### tx_succeeded (Python only)

Check if a receipt indicates success. TypeScript: check `receipt.status === "success"`.

```python
if wallet.tx_succeeded(receipt):
    print("Transaction confirmed")
```

### explorer_url / explorerUrl

Generate a block explorer link for a transaction.

**Python:**
```python
url = wallet.explorer_url(tx_hash)
# "https://testnet.radiustech.xyz/tx/0x..."
```

**TypeScript:**
```typescript
const url = wallet.explorerUrl(txHash);
```

## Faucet

### request_faucet / requestFaucet

Request tokens from the Radius faucet. Handles unsigned and signed flows automatically.

**Python:**
```python
result = wallet.request_faucet()         # Default: SBC
result = wallet.request_faucet("SBC")    # Explicit token
```

**TypeScript:**
```typescript
const result = await wallet.requestFaucet();
```

**Behavior:**
1. Attempts unsigned POST to `/drip`
2. If faucet requires signature: automatically fetches challenge, signs with EIP-191, and retries
3. If rate-limited: raises/throws with retry timing

For advanced faucet flows (manual challenge/sign, rate limit handling, mainnet-specific behavior), load the **dripping-faucet** skill.

## Contract Deployment

### deploy_contract / deployContract

Deploy a smart contract and wait for the receipt.

**Python** (string-based ABI encoding):
```python
result = wallet.deploy_contract(
    bytecode="0x608060...",                          # Hex-encoded bytecode
    constructor_types=["address", "uint256"],         # Solidity types (optional)
    constructor_args=["0xTokenAddr", 1000000],        # Values (optional)
)
# result: {"tx_hash": "0x...", "address": "0xContractAddr", "receipt": {...}}
```

**TypeScript** (typed ABI):
```typescript
const result = await wallet.deployContract(
  contractAbi,                    // Abi type from viem
  "0x608060..." as `0x${string}`, // Hex-encoded bytecode
  ["0xTokenAddr", 1000000n],      // Constructor args (optional)
);
// result: { txHash: "0x...", address: "0xContractAddr", receipt: {...} }
```

**Key difference:** Python takes `constructor_types` as strings (e.g., `["address", "uint256"]`) and encodes arguments manually. TypeScript takes a typed ABI and lets viem handle encoding.

## Contract Interaction — Read

### call_contract / readContract

Call a contract function without a transaction (read-only, no gas).

**Python** (string-based function signatures):
```python
# Read a uint256 value
count = wallet.call_contract(
    address="0xContract",
    function_sig="getCount()",
    return_types=["uint256"],
)
# count = 42

# Read with arguments
balance = wallet.call_contract(
    address="0xContract",
    function_sig="balanceOf(address)",
    arg_types=["address"],
    args=["0xHolder"],
    return_types=["uint256"],
)
```

**TypeScript** (typed ABI):
```typescript
const count = await wallet.readContract(
  "0xContract",
  contractAbi,
  "getCount",
);

const balance = await wallet.readContract(
  "0xContract",
  contractAbi,
  "balanceOf",
  ["0xHolder"],
);
```

## Contract Interaction — Write

### send_contract_tx / writeContract

Send a state-changing transaction to a contract. Returns the transaction hash.

**Python:**
```python
tx_hash = wallet.send_contract_tx(
    address="0xContract",
    function_sig="increment()",
)

# With arguments and custom gas
tx_hash = wallet.send_contract_tx(
    address="0xContract",
    function_sig="transfer(address,uint256)",
    arg_types=["address", "uint256"],
    args=["0xRecipient", 1000000],
    gas=200_000,       # Default: 100,000. Increase for complex calls.
)

receipt = wallet.wait_for_tx(tx_hash)
```

**TypeScript:**
```typescript
const txHash = await wallet.writeContract(
  "0xContract",
  contractAbi,
  "increment",
);

const txHash = await wallet.writeContract(
  "0xContract",
  contractAbi,
  "transfer",
  ["0xRecipient", 1000000n],
);

const receipt = await wallet.waitForTx(txHash);
```

## Chain Info

### get_chain_info / getChainInfo

Query chain ID, current block number, and gas price.

**Python:**
```python
info = wallet.get_chain_info()
# {"chain_id": 72344, "block_number": 1712345678000, "gas_price_gwei": 0.986, "note": "..."}
```

**TypeScript:**
```typescript
const info = await wallet.getChainInfo();
// { chainId: 72344, blockNumber: 1712345678000n, gasPriceGwei: "0.986" }
```

**Note:** On Radius, `block_number` is a timestamp in milliseconds, not a sequential block height.

## Exported Constants

**Python:**
```python
from radius_wallet import (
    TESTNET_RPC,        # "https://rpc.testnet.radiustech.xyz"
    MAINNET_RPC,        # "https://rpc.radiustech.xyz"
    TESTNET_CHAIN_ID,   # 72344
    MAINNET_CHAIN_ID,   # 723487
    TESTNET_EXPLORER,   # "https://testnet.radiustech.xyz"
    MAINNET_EXPLORER,   # "https://network.radiustech.xyz"
    SBC_ADDRESS,        # "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb"
    SBC_DECIMALS,       # 6
    RUSD_DECIMALS,      # 18
)
```

**TypeScript:**
```typescript
import {
  radiusTestnet,    // viem Chain definition (id: 72344)
  radiusMainnet,    // viem Chain definition (id: 723487)
  SBC_ADDRESS,      // "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb"
  SBC_DECIMALS,     // 6
  RUSD_DECIMALS,    // 18
  ERC20_ABI,        // ABI for balanceOf, transfer, decimals
} from "radius-wallet-ts";
```

## Raw JSON-RPC Fallback

Use these patterns **only** when the wallet library cannot be installed. The library is always preferred — it handles nonce management, ABI encoding, decimal conversion, and error handling.

### Check SBC balance

```python
import httpx

resp = httpx.post("https://rpc.testnet.radiustech.xyz", json={
    "jsonrpc": "2.0", "id": 1, "method": "eth_call",
    "params": [{
        "to": "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb",
        "data": "0x70a08231000000000000000000000000" + "YOUR_ADDRESS"[2:].lower().zfill(64)
    }, "latest"]
})
raw = int(resp.json()["result"], 16)
sbc_balance = raw / 1e6  # 6 decimals
```

### Send a native RUSD transfer

```python
from eth_account import Account

account = Account.from_key("0xYOUR_KEY")
tx = {
    "to": "0xRecipient",
    "value": int(0.001 * 1e18),  # 18 decimals
    "gas": 21000,
    "gasPrice": 986000000,       # ~1 gwei fixed
    "nonce": ...,                # Query eth_getTransactionCount
    "chainId": 72344,
}
signed = account.sign_transaction(tx)
resp = httpx.post("https://rpc.testnet.radiustech.xyz", json={
    "jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction",
    "params": ["0x" + signed.raw_transaction.hex()]
})
tx_hash = resp.json()["result"]
```

### Check transaction receipt

```python
resp = httpx.post("https://rpc.testnet.radiustech.xyz", json={
    "jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt",
    "params": ["0xTX_HASH"]
})
receipt = resp.json()["result"]  # None if pending
success = receipt and int(receipt["status"], 16) == 1
```
