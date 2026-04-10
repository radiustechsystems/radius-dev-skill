# Radius Network Reference

All constants, addresses, and behavioral differences an agent needs to operate on Radius.

## Network Endpoints

| Setting | Testnet | Mainnet |
|---------|---------|---------|
| Chain ID | 72344 | 723487 |
| RPC URL | `https://rpc.testnet.radiustech.xyz` | `https://rpc.radiustech.xyz` |
| Explorer | `https://testnet.radiustech.xyz` | `https://network.radiustech.xyz` |
| Faucet API | `https://testnet.radiustech.xyz/api/v1/faucet` | `https://network.radiustech.xyz/api/v1/faucet` |
| Faucet Web | `https://testnet.radiustech.xyz/wallet` | `https://network.radiustech.xyz/wallet` |

Mainnet RPC supports optional API key suffix: `https://rpc.radiustech.xyz/YOUR_API_KEY`

## Token Reference

| Token | Type | Address | Decimals | Notes |
|-------|------|---------|----------|-------|
| RUSD | Native | *(native balance)* | 18 | Used for gas; obtained automatically via Turnstile |
| SBC | ERC-20 | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | 6 | Primary payment token; same address on testnet and mainnet |

**Decimal rule:** SBC amounts use 6 decimals (1.0 SBC = 1,000,000 base units). RUSD amounts use 18 decimals. The wallet libraries handle conversion automatically when passing human-readable amounts (e.g., `1.5`).

## Key Deployed Contracts

| Contract | Address | Notes |
|----------|---------|-------|
| SBC Token | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | Same on testnet and mainnet |
| Permit2 | `0x000000000022D473030F116dDEE9F6B43aC78BA3` | Canonical Uniswap Permit2 |
| Multicall3 | `0xcA11bde05977b3631167028862bE2a173976CA11` | Standard Multicall3 |
| CreateX | `0xba5Ed099633D3B313e4D5F7bfe1D1E17A40ca5Ed` | Deterministic deployment factory |

## Gas and Fees

- **Fixed gas price**: ~986,000,000 wei (~1 gwei). No EIP-1559, no priority fees, no gas bidding.
- **Cost per standard transfer**: ~0.0001 USD
- **Failed transactions**: No gas charged on revert. Only successful transactions pay gas.
- **Turnstile**: If the wallet holds SBC but insufficient RUSD for gas, the network automatically converts SBC to RUSD. Minimum trigger: 0.1 SBC. Maximum per trigger: 10.0 SBC.

## Radius vs. Ethereum Differences

Only agent-relevant differences listed here. For the full comparison table, see the radius-dev skill.

| Feature | Ethereum | Radius |
|---------|----------|--------|
| Fee model | Market-based ETH gas bids | Fixed ~0.0001 USD via Turnstile |
| Settlement | ~12 min (12+ confirmations) | Sub-second finality (~200-500ms) |
| Failed txs | Charge gas even if reverted | No gas charged on failure |
| Reorgs | Possible | Impossible |
| `eth_gasPrice` | Market rate | Fixed price (~986M wei) |
| `eth_blockNumber` | Monotonic block height | Current timestamp in milliseconds |
| `eth_getLogs` | Address filter optional | Address filter **required** (error `-33014`) |
| Historical state | Queryable by block number | Only `latest`/`pending`/`safe`/`finalized` supported |

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `RADIUS_PRIVATE_KEY` | Wallet private key (0x-prefixed, 64 hex chars) | Yes |
| `RADIUS_RPC_URL` | Override default RPC endpoint | No |
| `RADIUS_CHAIN_ID` | Override default chain ID | No |

**Security:** Never log, print, or pass `RADIUS_PRIVATE_KEY` as a CLI argument. Load from environment only. Ensure `.env` is in `.gitignore`.

## Faucet Quick Reference

| Setting | Testnet | Mainnet |
|---------|---------|---------|
| Drip amount | ~0.5 SBC | ~0.01 SBC |
| Rate limit | 60 requests/minute | 1 request/day |
| Signature required | Not currently (may change) | Always |
| Library call | `wallet.request_faucet()` | `wallet.request_faucet()` (auto-signs) |

The wallet libraries handle unsigned/signed flows automatically. For advanced faucet control (manual challenge/sign, rate limit handling, error mapping), load the **dripping-faucet** skill.

## Live Documentation

For current network configuration and API details: `https://docs.radiustech.xyz/llms-full.txt`
