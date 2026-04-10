---
name: radius-agent-ops
description: |
  This skill should be used when the user asks to "check balance on Radius",
  "check my wallet balance", "send SBC", "send RUSD", "transfer tokens on Radius",
  "deploy a contract on Radius", "call a smart contract", "read contract state",
  "write to a contract", "check transaction status", "get a transaction receipt",
  "verify a transaction on Radius", "get chain info on Radius",
  "use radius-wallet-py", "use radius-wallet-ts", or needs to perform on-chain
  operations programmatically using the Radius wallet libraries. Covers wallet setup,
  balance queries, token transfers, contract deployment and interaction, and transaction
  verification. Not for dApp UI development with wagmi/React (use radius-dev), x402
  HTTP payment protocol (use x402), or dedicated faucet flows (use dripping-faucet).
user-invocable: true
---

# Radius Agent Operations

Perform on-chain operations on the Radius network from agent code: check balances, send tokens, deploy and interact with smart contracts, and verify transactions.

## When to Use

- Check RUSD or SBC token balances
- Send SBC (ERC-20) or RUSD (native) transfers
- Deploy a smart contract from bytecode
- Read from or write to a deployed contract
- Check transaction status or get a receipt
- Query Radius network info (chain ID, gas price, block number)

**Not this Skill:** For dApp development with wagmi, React, or Foundry project setup, use the **radius-dev** skill. For x402 HTTP micropayment protocol, use the **x402** skill. For dedicated faucet token requests with full error handling, use the **dripping-faucet** skill.

## Install the Wallet Library First

Do NOT write custom JSON-RPC calls, raw HTTP requests, or manual ABI encoding. The wallet libraries handle RPC communication, ABI encoding, decimal conversion, gas estimation, and nonce management.

**Python** (recommended for agent frameworks):

```bash
pip install git+https://github.com/radiustechsystems/radius-wallet-py.git
```

**TypeScript:**

```bash
npm install github:radiustechsystems/radius-wallet-ts
```

**Environment setup:**

```bash
export RADIUS_PRIVATE_KEY=0x...   # 0x-prefixed, 64 hex characters
```

Never log, print, or pass the private key as a CLI argument. Always load from the environment variable.

## Quick Reference

| Operation | Python | TypeScript |
|-----------|--------|------------|
| Create wallet | `RadiusWallet.create()` | `RadiusWallet.create()` |
| Load from env | `RadiusWallet.from_env()` | `RadiusWallet.fromEnv()` |
| Check balances | `wallet.get_balances()` | `await wallet.getBalances()` |
| Get SBC balance | `wallet.get_sbc_balance()` | `await wallet.getSbcBalance()` |
| Get RUSD balance | `wallet.get_rusd_balance()` | `await wallet.getRusdBalance()` |
| Send SBC | `wallet.send_sbc(to, amount)` | `await wallet.sendSbc(to, amount)` |
| Send RUSD | `wallet.send_rusd(to, amount)` | `await wallet.sendRusd(to, amount)` |
| Request faucet | `wallet.request_faucet()` | `await wallet.requestFaucet()` |
| Wait for tx | `wallet.wait_for_tx(hash)` | `await wallet.waitForTx(hash)` |
| Check tx success | `wallet.tx_succeeded(receipt)` | `receipt.status === "success"` |
| Explorer link | `wallet.explorer_url(hash)` | `wallet.explorerUrl(hash)` |
| Deploy contract | `wallet.deploy_contract(bytecode, ...)` | `await wallet.deployContract(abi, bytecode, ...)` |
| Read contract | `wallet.call_contract(addr, sig, ...)` | `await wallet.readContract(addr, abi, fn, ...)` |
| Write contract | `wallet.send_contract_tx(addr, sig, ...)` | `await wallet.writeContract(addr, abi, fn, ...)` |
| Chain info | `wallet.get_chain_info()` | `await wallet.getChainInfo()` |

For complete method signatures, parameters, and return types, consult [`references/wallet-api.md`](references/wallet-api.md).

## Radius Network Essentials

| | Testnet | Mainnet |
|-|---------|---------|
| Chain ID | 72344 | 723487 |
| RPC | `https://rpc.testnet.radiustech.xyz` | `https://rpc.radiustech.xyz` |
| Explorer | `https://testnet.radiustech.xyz` | `https://network.radiustech.xyz` |
| SBC Address | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | Same |

**Critical Radius behavior:**

- **SBC uses 6 decimals, RUSD uses 18.** The libraries handle conversion when passing human-readable amounts (e.g., `1.5`). For raw values, 1.0 SBC = 1,000,000 base units.
- **Fixed gas pricing.** No EIP-1559, no priority fees. Gas price is ~1 gwei.
- **Sub-second finality.** Transactions confirm in ~200-500ms. No reorgs possible.
- **Failed transactions do not charge gas.** Only successful transactions pay.
- **Block numbers are timestamps in milliseconds.** Not sequential block heights.
- **Turnstile auto-converts SBC to RUSD for gas.** If the wallet has SBC but insufficient RUSD, the network converts automatically (min 0.1 SBC, max 10.0 SBC per trigger).

For the full network reference (deployed contracts, Radius vs. Ethereum differences, faucet details), consult [`references/network-reference.md`](references/network-reference.md).

## Core Workflows

### Check Balances

```python
from radius_wallet import RadiusWallet

wallet = RadiusWallet.from_env()
balances = wallet.get_balances()
print(f"Address: {balances['address']}")
print(f"SBC: {balances['sbc']}")
print(f"RUSD: {balances['rusd']}")
```

### Send SBC and Verify

```python
from radius_wallet import RadiusWallet

wallet = RadiusWallet.from_env()
tx_hash = wallet.send_sbc("0xRecipientAddress", 1.5)  # 1.5 SBC
receipt = wallet.wait_for_tx(tx_hash)

if wallet.tx_succeeded(receipt):
    print(f"Sent! {wallet.explorer_url(tx_hash)}")
else:
    print("Transaction failed")
```

### Deploy and Interact with a Contract

```python
from radius_wallet import RadiusWallet

wallet = RadiusWallet.from_env()

# Deploy (use pre-compiled bytecode or load from Foundry artifact)
result = wallet.deploy_contract("0x608060...")
contract = result["address"]
print(f"Deployed at {contract}")
print(f"Explorer: {wallet.explorer_url(result['tx_hash'])}")

# Read state
count = wallet.call_contract(contract, "getCount()", return_types=["uint256"])
print(f"Count: {count}")

# Write state
tx = wallet.send_contract_tx(contract, "increment()")
wallet.wait_for_tx(tx)

# Verify
count = wallet.call_contract(contract, "getCount()", return_types=["uint256"])
print(f"Count after increment: {count}")
```

For detailed contract patterns (constructor args, ERC-20 approve flows, Foundry CLI deployment, workshop contracts), consult [`references/contract-patterns.md`](references/contract-patterns.md).

### Check Transaction Status

```python
from radius_wallet import RadiusWallet

wallet = RadiusWallet.from_env()

# Quick check (returns None if pending)
receipt = wallet.get_tx_receipt("0xTxHash...")

# Block until confirmed (with timeout)
receipt = wallet.wait_for_tx("0xTxHash...", timeout=30.0)

if wallet.tx_succeeded(receipt):
    print(f"Success: {wallet.explorer_url('0xTxHash...')}")
else:
    print("Transaction reverted")
```

### Fund a Wallet (Faucet)

To request test tokens, call the one-liner:

```python
wallet.request_faucet()  # Handles unsigned + signed flows automatically
```

For advanced faucet control (manual challenge/sign, mainnet tokens, rate limit handling), load the **dripping-faucet** skill.

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Writing custom JSON-RPC or raw HTTP calls | Install and use `radius-wallet-py` or `radius-wallet-ts` |
| Using 18 decimals for SBC amounts | SBC uses 6 decimals. The library handles conversion automatically. |
| Bash state not persisting between agent tool calls | Run the complete flow in a single Python script, not across separate shell commands |
| Not waiting for transaction confirmation | Always call `wait_for_tx(hash)` and check `tx_succeeded(receipt)` |
| Logging or displaying the private key | Load from `RADIUS_PRIVATE_KEY` env var only. Never print or pass as CLI arg. |
| Mainnet faucet without signature | The library handles signing automatically. For manual flows, a signature is always required on mainnet. |

## Additional Resources

### Reference Files

- **[`references/wallet-api.md`](references/wallet-api.md)** — Complete API reference for both Python and TypeScript wallet libraries, including method signatures, return types, and raw JSON-RPC fallback
- **[`references/contract-patterns.md`](references/contract-patterns.md)** — Contract deployment, interaction, ERC-20 approve patterns, and workshop contract examples
- **[`references/network-reference.md`](references/network-reference.md)** — Network constants, deployed contracts, gas details, and Radius vs. Ethereum differences

### Related Skills

- **dripping-faucet** — Advanced faucet flows (signed/unsigned, mainnet, rate limit handling, error mapping)
- **radius-dev** — dApp development (wagmi, React, Foundry project setup, event watching, micropayment architecture)
- **x402** — HTTP micropayment protocol (payment gating, EIP-2612 permits, facilitator integration)

### Live Documentation

For current network configuration and API details: `https://docs.radiustech.xyz/llms-full.txt`
