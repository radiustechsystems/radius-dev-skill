---
name: radius-agent-ops
description: |
  This skill should be used when the user asks to "check balance on Radius",
  "check my wallet balance", "send SBC", "send RUSD", "transfer tokens on Radius",
  "deploy a contract on Radius", "call a smart contract", "read contract state",
  "write to a contract", "check transaction status", "get a transaction receipt",
  "verify a transaction on Radius", or "get chain info on Radius".
  Covers direct on-chain operations with general EVM tooling. Not for dApp UI
  development with wagmi/React (use radius-dev), x402 HTTP payment protocol
  (use x402), or dedicated faucet flows (use dripping-faucet).
user-invocable: true
---

# Radius Agent Operations

Perform simple on-chain operations on Radius: check balances, send tokens, deploy and interact with contracts, and verify transactions.

## When to Use

- Check RUSD or SBC balances
- Send SBC (ERC-20) or RUSD (native) transfers
- Check transaction receipts and success/failure
- Deploy a contract from bytecode and call contract functions
- Query chain details (chain ID, gas price, block number behavior)

**Not this Skill:** For dApp development with wagmi, React, or Foundry project setup, use the **radius-dev** skill. For x402 HTTP micropayment protocol, use the **x402** skill. For dedicated faucet token requests with full error handling, use the **dripping-faucet** skill.

## Tooling Precedence

Use this order unless the user requests a specific tool:

1. `cast` (CLI-first for quick actions)
2. `web3.py` (Python automation fallback)
3. `viem` (TypeScript automation fallback)

Do not require project-specific wallet wrapper libraries for this skill.

## Setup and Security

```bash
# Network defaults (testnet)
export RADIUS_RPC_URL=https://rpc.testnet.radiustech.xyz
export RADIUS_CHAIN_ID=72344
export SBC_ADDRESS=0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb

# Signing key
export RADIUS_PRIVATE_KEY=0x...  # 0x-prefixed, 64 hex chars
```

- Store keys in environment variables or a keystore.
- Never print private keys in output.
- Never hardcode keys in scripts.
- Keep `.env` out of git.

## Quick Action Reference

| Operation | `cast` default | `web3.py` fallback | `viem` fallback |
|-----------|----------------|--------------------|-----------------|
| Wallet address | `cast wallet address --private-key "$RADIUS_PRIVATE_KEY"` | `Account.from_key(...)` | `privateKeyToAccount(...)` |
| RUSD balance | `cast balance <addr> --rpc-url "$RADIUS_RPC_URL"` | `w3.eth.get_balance(addr)` | `publicClient.getBalance({ address })` |
| SBC balance | `cast call $SBC_ADDRESS "balanceOf(address)(uint256)" <addr> --rpc-url "$RADIUS_RPC_URL"` | `token.functions.balanceOf(addr).call()` | `readContract(balanceOf)` |
| Send SBC | `cast send $SBC_ADDRESS "transfer(address,uint256)" <to> <amount_6dp> ...` | `token.functions.transfer(...).build_transaction(...)` | `walletClient.writeContract(...)` |
| Send RUSD | `cast send <to> --value <wei> ...` | `w3.eth.send_raw_transaction(...)` | `walletClient.sendTransaction(...)` |
| Tx status | `cast receipt <tx_hash> --rpc-url "$RADIUS_RPC_URL"` | `w3.eth.get_transaction_receipt(...)` | `waitForTransactionReceipt(...)` |
| Deploy bytecode | `cast send --create <bytecode> ...` | `Contract.constructor(...).build_transaction(...)` | `walletClient.deployContract(...)` |
| Read contract | `cast call <addr> "fn(sig)(ret)" ...` | `contract.functions.fn(...).call()` | `publicClient.readContract(...)` |
| Write contract | `cast send <addr> "fn(sig)" ...` | `contract.functions.fn(...).build_transaction(...)` | `walletClient.writeContract(...)` |

For copy-paste workflows with all three tooling paths, see [`references/core-workflows.md`](references/core-workflows.md).

## Radius Network Essentials

| | Testnet | Mainnet |
|-|---------|---------|
| Chain ID | 72344 | 723487 |
| RPC | `https://rpc.testnet.radiustech.xyz` | `https://rpc.radiustech.xyz` |
| Explorer | `https://testnet.radiustech.xyz` | `https://network.radiustech.xyz` |
| SBC Address | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | Same |

**Critical Radius behavior:**

- **SBC uses 6 decimals, RUSD uses 18.** Convert amounts correctly.
- **Fixed gas pricing.** No EIP-1559, no priority fees.
- **Sub-second finality.** Transactions typically confirm in ~200-500ms.
- **Failed transactions do not charge gas.** Only successful transactions pay.
- **Block numbers are timestamps in milliseconds.** Not sequential heights.
- **Turnstile auto-converts SBC to RUSD for gas** under network limits.

For full constants and behavior details, see [`references/network-reference.md`](references/network-reference.md).

## Core Workflows

### Check Balances

```bash
ADDR=$(cast wallet address --private-key "$RADIUS_PRIVATE_KEY")
cast balance "$ADDR" --rpc-url "$RADIUS_RPC_URL"
cast call "$SBC_ADDRESS" "balanceOf(address)(uint256)" "$ADDR" --rpc-url "$RADIUS_RPC_URL"
```

### Send SBC and Verify

```bash
# 0.5 SBC = 500000 base units (6 decimals)
TX_HASH=$(cast send "$SBC_ADDRESS" \
  "transfer(address,uint256)" \
  0xRecipientAddress \
  500000 \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$TX_HASH" --rpc-url "$RADIUS_RPC_URL"
```

### Send RUSD and Verify

```bash
# 0.001 RUSD = 1000000000000000 wei
TX_HASH=$(cast send 0xRecipientAddress \
  --value 1000000000000000 \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$TX_HASH" --rpc-url "$RADIUS_RPC_URL"
```

### Check Transaction Status

```bash
cast receipt 0xTxHash --rpc-url "$RADIUS_RPC_URL"
# status=1 success, status=0 revert
```

Explorer link format:

```text
https://testnet.radiustech.xyz/tx/<tx_hash>
https://network.radiustech.xyz/tx/<tx_hash>
```

### Deploy and Interact with a Contract

```bash
BYTECODE=0x608060...
DEPLOY_TX=$(cast send --create "$BYTECODE" --rpc-url "$RADIUS_RPC_URL" --private-key "$RADIUS_PRIVATE_KEY")

# Read function
cast call 0xContractAddress "getCount()(uint256)" --rpc-url "$RADIUS_RPC_URL"

# Write function
WRITE_TX=$(cast send 0xContractAddress "increment()" --rpc-url "$RADIUS_RPC_URL" --private-key "$RADIUS_PRIVATE_KEY")
cast receipt "$WRITE_TX" --rpc-url "$RADIUS_RPC_URL"
```

For detailed deployment and interaction patterns (approve flows, constructor args, workshop contracts), see [`references/contract-patterns.md`](references/contract-patterns.md).

### Fund a Wallet (Faucet)

For faucet flows, use the **dripping-faucet** skill.

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Using 18 decimals for SBC | SBC uses 6 decimals. Convert to base units correctly. |
| Not waiting for receipts | Always fetch receipt and verify `status`. |
| Logging private key | Use env vars or keystore only, never print secrets. |
| Assuming Ethereum block-number semantics | Radius `eth_blockNumber` is a timestamp in ms. |
| Using mainnet by accident | Set `RADIUS_RPC_URL` and `RADIUS_CHAIN_ID` explicitly at start. |
| Defaulting to raw JSON-RPC | Use `cast`, `web3.py`, or `viem` first; raw RPC is last-resort troubleshooting. |

## Additional Resources

### Reference Files

- **[`references/core-workflows.md`](references/core-workflows.md)** — Task-oriented workflows for `cast`, `web3.py`, and `viem`
- **[`references/contract-patterns.md`](references/contract-patterns.md)** — Contract deployment/interaction patterns and ERC-20 approve flows
- **[`references/network-reference.md`](references/network-reference.md)** — Network constants, gas behavior, and Radius vs Ethereum differences

### Related Skills

- **dripping-faucet** — Advanced faucet flows (signed/unsigned, mainnet, rate limit handling, error mapping)
- **radius-dev** — dApp development (wagmi, React, Foundry project setup, event watching, micropayment architecture)
- **x402** — HTTP micropayment protocol (payment gating, EIP-2612 permits, facilitator integration)

### Live Documentation

For current network configuration and API details: `https://docs.radiustech.xyz/llms-full.txt`
