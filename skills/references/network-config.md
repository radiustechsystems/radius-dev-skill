# Network Configuration & RPC Reference

## Radius Network (mainnet)

| Setting | Value |
|---------|-------|
| **Network Name** | Radius Network |
| **RPC Endpoint** | `https://rpc.radiustech.xyz` |
| **Chain ID** | `723` (hex: `0x2D3`) |
| **Currency Symbol** | RUSD |
| **Currency Decimals** | 18 |
| **Block Explorer** | `https://network.radiustech.xyz` |
| **Faucet** | Not available on mainnet |
| **Dashboard** | `https://network.radiustech.xyz` |

## Radius Testnet

| Setting | Value |
|---------|-------|
| **Network Name** | Radius Testnet |
| **RPC Endpoint** | `https://rpc.testnet.radiustech.xyz` |
| **Chain ID** | `72344` (hex: `0x11a98`) |
| **Currency Symbol** | RUSD |
| **Currency Decimals** | 18 |
| **Block Explorer** | `https://testnet.radiustech.xyz` |
| **Faucet** | `https://testnet.radiustech.xyz/testnet/faucet` |
| **Dashboard** | `https://testnet.radiustech.xyz` |

## Chain definition (viem)

### Mainnet

```typescript
import { defineChain } from 'viem';

export const radiusNetwork = defineChain({
  id: 723,
  name: 'Radius Network',
  nativeCurrency: {
    decimals: 18,
    name: 'RUSD',
    symbol: 'RUSD',
  },
  rpcUrls: {
    default: {
      http: ['https://rpc.radiustech.xyz'],
    },
  },
  blockExplorers: {
    default: {
      name: 'Radius Explorer',
      url: 'https://network.radiustech.xyz',
    },
  },
  fees: {
    async estimateFeesPerGas() {
      const res = await fetch(
        'https://network.radiustech.xyz/api/v1/network/transaction-cost'
      );
      const { gas_price_wei } = await res.json();
      return { gasPrice: BigInt(gas_price_wei) };
    },
  },
});
```

### Testnet

```typescript
import { defineChain } from 'viem';

export const radiusTestnet = defineChain({
  id: 72344,
  name: 'Radius Testnet',
  nativeCurrency: {
    decimals: 18,
    name: 'RUSD',
    symbol: 'RUSD',
  },
  rpcUrls: {
    default: {
      http: ['https://rpc.testnet.radiustech.xyz'],
    },
  },
  blockExplorers: {
    default: {
      name: 'Radius Explorer',
      url: 'https://testnet.radiustech.xyz',
    },
  },
  fees: {
    async estimateFeesPerGas() {
      const res = await fetch(
        'https://testnet.radiustech.xyz/api/v1/network/transaction-cost'
      );
      const { gas_price_wei } = await res.json();
      return { gasPrice: BigInt(gas_price_wei) };
    },
  },
});
```

> **Important:** Always define `fees.estimateFeesPerGas()` in your chain definition. If tooling derives zero or invalid fee values, transactions fail silently. Do not use `@radiustechsystems/sdk` — use plain viem `defineChain` as shown above.

## Add to MetaMask (programmatic)

### Mainnet

```javascript
await window.ethereum.request({
  method: 'wallet_addEthereumChain',
  params: [{
    chainId: '0x2D3',
    chainName: 'Radius Network',
    nativeCurrency: {
      name: 'RUSD',
      symbol: 'RUSD',
      decimals: 18,
    },
    rpcUrls: ['https://rpc.radiustech.xyz'],
    blockExplorerUrls: ['https://network.radiustech.xyz'],
  }],
});
```

### Testnet

```javascript
await window.ethereum.request({
  method: 'wallet_addEthereumChain',
  params: [{
    chainId: '0x11a98',
    chainName: 'Radius Testnet',
    nativeCurrency: {
      name: 'RUSD',
      symbol: 'RUSD',
      decimals: 18,
    },
    rpcUrls: ['https://rpc.testnet.radiustech.xyz'],
    blockExplorerUrls: ['https://testnet.radiustech.xyz'],
  }],
});
```

> **Wallet compatibility:** MetaMask is the only wallet that reliably adds and switches to Radius. Coinbase Wallet, Trust Wallet, and Rainbow may reject adding unknown chains. See [gotchas.md](gotchas.md) for handling both error code 4902 and -32603.

## Add to MetaMask (manual)

1. Open MetaMask and select **Add Network**
2. Enter the settings from the appropriate network table above
3. Save and switch to the Radius network

## Get testnet funds

1. Visit the [Radius Testnet Faucet](https://testnet.radiustech.xyz/testnet/faucet)
2. Connect your wallet or paste a testnet address
3. Claim tokens (instant)
4. Wait ~30 seconds for confirmation

Testnet tokens have no real value. Use them freely to learn and test.

---

## Contract Addresses

### Core contracts

| Contract | Network | Address | Decimals | Description |
|----------|---------|---------|----------|-------------|
| **SBC Token** | Mainnet | `0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb` | **6** | ERC-20 stablecoin for transfers and gas-fee conversion. **NOT 18 decimals.** |
| **radUSD Token** | Testnet | `0xF966020a30946A64B39E2e243049036367590858` | 18 | Stablecoin used for gas fees on Radius Testnet |

> **Critical:** SBC uses **6 decimals**. RUSD (native token) uses 18 decimals. Confusing the two is the most common mistake. Always use `parseUnits(amount, 6)` for SBC and `parseEther(amount)` for RUSD. See [gotchas.md](gotchas.md#1-sbc-uses-6-decimals-not-18).

#### SBC EIP-712 domain (for permits)

```typescript
const domain = {
  name: 'SBC',           // Exactly "SBC" — not "SBC Token"
  version: '1',          // String "1", not number 1
  chainId: 723,          // Mainnet chain ID
  verifyingContract: '0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb',
};
```

### Utility contracts (testnet)

| Contract | Address | Description |
|----------|---------|-------------|
| **Arachnid Create2 Factory** | `0x4e59b44847b379578588920cA78FbF26c0B4956C` | Deploy contracts to deterministic addresses using CREATE2 |
| **CreateX** | `0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed` | Advanced deployment factory (CREATE, CREATE2, CREATE3) with cross-chain address prediction |
| **Multicall3** | `0xcA11bde05977b3631167028862bE2a173976CA11` | Aggregate multiple contract reads into a single RPC call |
| **Permit2** | `0x000000000022D473030F116dDEE9F6B43aC78BA3` | Unified token approval system (Uniswap). Gasless approvals via signatures, batched transfers |

### Utility contracts (mainnet)

| Contract | Address | Description |
|----------|---------|-------------|
| **Arachnid Create2 Factory** | `0x4e59b44847b379578588920cA78FbF26c0B4956C` | Deploy contracts to deterministic addresses using CREATE2 |
| **Permit2** | `0x000000000022D473030F116dDEE9F6B43aC78BA3` | Unified token approval system (Uniswap). Gasless approvals via signatures, batched transfers |
| **Multicall3** | `0xcA11bde05977b3631167028862bE2a173976CA11` | Aggregate multiple contract reads into a single RPC call |
| **CreateX** | `0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed` | Advanced deployment factory (CREATE, CREATE2, CREATE3) with cross-chain address prediction |

### Account Abstraction contracts (testnet)

| Contract | Address |
|----------|---------|
| **EntryPoint v0.7** | `0x9b443e4bd122444852B52331f851a000164Cc83F` |
| **SimpleAccountFactory** | `0x4DEbDe0Be05E51432D9afAf61D84F7F0fEA63495` |

---

## Transaction Cost API

Use this endpoint to fetch current fee data programmatically.

| Network | Endpoint |
|---------|----------|
| **Testnet** | `https://testnet.radiustech.xyz/api/v1/network/transaction-cost` |
| **Mainnet** | `https://network.radiustech.xyz/api/v1/network/transaction-cost` |

**Example response:**

```json
{
  "cost_usd": 0.000092887004460096,
  "gas_price_wei": "0x3ac525e0",
  "gas_used": 101444,
  "last_updated": 1772078216407
}
```

| Field | Type | Description |
|-------|------|-------------|
| `cost_usd` | `number` | Average transaction cost in USD |
| `gas_price_wei` | `string` | Current gas price in wei (hex-encoded) |
| `gas_used` | `number` | Gas consumed by an average stablecoin transfer |
| `last_updated` | `number` | Unix timestamp in milliseconds of the last update |

Use `gas_price_wei` to drive `fees.estimateFeesPerGas()` in viem chain definitions.

---

## RPC API keys and rate limiting

Radius tracks request volume per API key.

- Requests without an API key have lower limits.
- Default API key limit is **10 MGas/s** (includes both RPC calls and gas consumed by submitted transactions).
- For higher limits, contact [support@radiustech.xyz](mailto:support@radiustech.xyz).

### RPC key URL format

Append your API key to the RPC URL path:

```
https://rpc.radiustech.xyz/{{API_KEY}}
```

### WebSocket RPC

WebSocket RPC requires an API key with elevated privileges. Supports `logs` subscriptions only (`newHeads` and `newPendingTransactions` are not available).

For access requests, contact [support@radiustech.xyz](mailto:support@radiustech.xyz).

---

## JSON-RPC API

Radius exposes a JSON-RPC 2.0 API compatible with standard Ethereum tooling. All standard `eth_*` methods are supported.

### Quick test

```bash
curl -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}'
```

Response:

```json
{"jsonrpc":"2.0","id":1,"result":"0x11a98"}
```

### Standard methods

All standard Ethereum JSON-RPC methods are supported. See [evm-differences.md](evm-differences.md) for methods that behave differently on Radius.

**Account & state:**
- `eth_chainId`
- `eth_blockNumber`
- `eth_getBalance` — Returns native + convertible USD balance
- `eth_getTransactionCount`
- `eth_getCode`
- `eth_getStorageAt`

**Transactions:**
- `eth_sendRawTransaction`
- `eth_call`
- `eth_estimateGas`
- `eth_getTransactionByHash`
- `eth_getTransactionReceipt`

**Blocks:**
- `eth_getBlockByNumber`
- `eth_getBlockByHash` — Pseudo-supported (Radius does not index by hash traditionally)

**Logs & filters:**
- `eth_getLogs`
- `eth_subscribe` — WebSocket only
- `eth_uninstallFilter` — Always returns `true`
- `eth_createAccessList`

**Gas & fees:**
- `eth_gasPrice` — Returns fixed gas price (~986M wei, ~1 gwei)
- `eth_maxPriorityFeePerGas` — Returns `0x0`
- `eth_feeHistory` — Pseudo-supported (stablecoin fees)

**Network info:**
- `web3_clientVersion`
- `web3_sha3`
- `net_version` — Returns `72344`
- `net_listening` — Always `false`
- `net_peerCount` — Always `0x0`
- `eth_accounts` — Always `[]`
- `eth_mining` — Always `true`
- `eth_syncing` — Always `false`
- `eth_hashrate` — Always `0x0`

**Tracing:**
- `trace_call` — Execute a call and retrieve detailed trace information (Parity-compatible)

### Radius-specific methods: `dash_*`

Dashboard methods for monitoring and analytics.

#### dash_globalGasUsage

Get total gas usage across the system.

```bash
curl -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"dash_globalGasUsage","params":[],"id":1}'
```

Returns: `number` — Total gas usage as a floating-point number.

#### dash_globalTps

Get current transactions per second across the system.

```bash
curl -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"dash_globalTps","params":[],"id":1}'
```

Returns: `number` — TPS as a floating-point number.

Example response:

```json
{"jsonrpc":"2.0","id":1,"result":26.486095339407825}
```

#### dash_latestTransactions

Get the most recent transactions.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| count | `number` | Number of transactions to return |

**Returns:** `array` — Array of compact transaction objects with fields: `hash`, `from`, `to`, `value`, `ts`, `success`.

```bash
curl -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"dash_latestTransactions","params":[10],"id":1}'
```

#### dash_findTransactionsByAddress

Get transactions involving a specific address.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| address | `string` | Address to query |

```bash
curl -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"dash_findTransactionsByAddress","params":["0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"],"id":1}'
```

### Radius-specific methods: `rad_*`

Debugging and utility methods.

#### rad_decodeKey

Decode a hashed key by monitoring broker operations and returning the matching raw key.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| key | `string` | Hashed key to decode |

**Returns:** `string` — The decoded raw key.

```bash
curl -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"rad_decodeKey","params":["0x..."],"id":1}'
```

### Error codes

Standard JSON-RPC 2.0 error codes:

| Code | Message | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid request | Invalid request object |
| -32601 | Method not found | Method does not exist |
| -32602 | Invalid params | Invalid method parameters |
| -32603 | Internal error | Internal JSON-RPC error |
| 3 | Execution reverted | Contract execution reverted |

---

### Unsupported methods

Radius returns errors for these methods:

- `eth_coinbase`
- `eth_getBlockReceipts`
- `eth_getFilterChanges`
- `eth_getFilterLogs`
- `eth_getProof`
- `eth_getUncleByBlockHashAndIndex`
- `eth_getUncleByBlockNumberAndIndex`
- `eth_getUncleCountByBlockHash`
- `eth_getUncleCountByBlockNumber`
- `eth_getWork`
- `eth_newBlockFilter`
- `eth_newFilter`
- `eth_newPendingTransactionFilter`
- `eth_sign`
- `eth_simulateV1`
- `eth_submitWork`
- `trace_block`
- `trace_callMany`
- `trace_filter`
- `trace_transaction`

---

## Verify connectivity

Quick check to verify your connection to Radius Testnet:

```typescript
import { createPublicClient, http, defineChain } from 'viem';

// Use the radiusTestnet chain definition from the "Chain definition" section above
const radiusTestnet = defineChain({
  id: 72344,
  name: 'Radius Testnet',
  nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
  rpcUrls: { default: { http: ['https://rpc.testnet.radiustech.xyz'] } },
  fees: {
    async estimateFeesPerGas() {
      const res = await fetch(
        'https://testnet.radiustech.xyz/api/v1/network/transaction-cost'
      );
      const { gas_price_wei } = await res.json();
      return { gasPrice: BigInt(gas_price_wei) };
    },
  },
});

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const chainId = await publicClient.getChainId();
console.log('Chain ID:', chainId); // 72344

const blockNumber = await publicClient.getBlockNumber();
console.log('Block number:', blockNumber); // NOTE: this is a timestamp in ms, not a sequential height
```

Or via curl:

```bash
# Chain ID
curl -s -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' | jq .result

# Latest block number (returns timestamp in milliseconds)
curl -s -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' | jq .result

# Gas price (returns fixed gas price, NOT 0x0)
curl -s -X POST https://rpc.testnet.radiustech.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_gasPrice","params":[],"id":1}' | jq .result

# Transaction cost API (most reliable fee data)
curl -s https://testnet.radiustech.xyz/api/v1/network/transaction-cost | jq .
```
