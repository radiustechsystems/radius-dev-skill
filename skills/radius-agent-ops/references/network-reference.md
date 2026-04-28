# Radius Network Reference

Constants and behavioral differences needed for simple Radius operations.

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
| RUSD | Native | *(native balance)* | 18 | Used for gas |
| SBC | ERC-20 | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | 6 | Same address on testnet and mainnet |

Decimal rule:

- SBC: 6 decimals (`1 SBC = 1,000,000` base units)
- RUSD: 18 decimals (`1 RUSD = 1e18` wei)

## Key Deployed Contracts

| Contract | Address | Notes |
|----------|---------|-------|
| SBC Token | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | Same on testnet and mainnet |
| Permit2 | `0x000000000022D473030F116dDEE9F6B43aC78BA3` | Canonical Uniswap Permit2 |
| Multicall3 | `0xcA11bde05977b3631167028862bE2a173976CA11` | Standard Multicall3 |
| CreateX | `0xba5Ed099633D3B313e4D5F7bfe1D1E17A40ca5Ed` | Deterministic deployment factory |

## Gas and Fees

- **Fixed gas price**: about `986,000,000` wei (about 1 gwei)
- **No EIP-1559 market mechanics**: no priority fee bidding
- **Failed transactions**: no gas charged on revert
- **Turnstile**: auto-converts SBC to RUSD for gas when eligible
  - Minimum trigger: `0.1 SBC`
  - Maximum per trigger: `10 SBC`

## Radius vs Ethereum Differences

| Feature | Ethereum | Radius |
|---------|----------|--------|
| Fee model | Market gas bidding | Fixed-price stablecoin gas |
| Settlement | Multi-block confirmation practice | Sub-second finality (~200-500ms) |
| Failed txs | Gas charged on revert | No gas charged on revert |
| Reorgs | Possible | Not possible |
| `eth_gasPrice` | Market value | Fixed value |
| `eth_blockNumber` | Monotonic block height | Timestamp in milliseconds |
| `eth_getLogs` | Address filter optional | Address filter required (`-33014`) |
| Historical state | Query by historical block | Only current tags supported |

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `RADIUS_PRIVATE_KEY` | Signing key (0x-prefixed, 64 hex chars) | Yes for writes |
| `RADIUS_RPC_URL` | RPC endpoint override | No |
| `RADIUS_CHAIN_ID` | Chain ID override | No |
| `SBC_ADDRESS` | SBC contract override (if needed) | No |

Security:

- Keep signing keys in env vars or keystore.
- Never print keys in logs.
- Keep `.env` out of source control.

## Faucet Quick Reference

| Setting | Testnet | Mainnet |
|---------|---------|---------|
| Drip amount | ~0.5 SBC | ~0.01 SBC |
| Rate limit | 60 requests/minute | 1 request/day |
| Signature required | Not currently (may change) | Always |
| Recommended path | `dripping-faucet` skill | `dripping-faucet` skill |

## Live Documentation

For current network configuration and API details: `https://docs.radiustech.xyz/llms-full.txt`
