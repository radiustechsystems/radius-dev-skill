# EVM Differences from Ethereum

## Overview

Radius is EVM-compatible — your Solidity contracts, Foundry toolchain, viem, wagmi, and OpenZeppelin libraries all work unchanged. However, Radius optimizes for payments and introduces deliberate differences from standard Ethereum behavior. This document covers everything you need to know.

## What works unchanged

| Tool/Framework | Status |
|---------------|--------|
| **Solidity** | Fully supported (Osaka hardfork via Revm 33.1.0) |
| **wagmi** | Compatible |
| **viem** | Compatible |
| **OpenZeppelin** | Compatible |
| **Foundry** | Compatible |
| **Standard precompiles** | 0x01 - 0x0a supported |

Deploy existing contracts with no modifications:

```bash
forge create src/MyContract.sol:MyContract \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --private-key $PRIVATE_KEY
```

Connect your application:

```typescript
import { createPublicClient, http, defineChain } from 'viem';

// Define Radius Testnet (see typescript-viem.md for the full chain definition with fees)
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
console.log('Connected to chain:', chainId); // 72344
```

## Key differences from Ethereum

| Feature | Ethereum | Radius |
|---------|----------|--------|
| **Fee model** | Market-based ETH gas bids | Fixed ~0.0001 USD per transaction |
| **Settlement time** | ~12 minutes (12+ confirmations) | Sub-second (~500ms finality) |
| **Failed txs** | Charge gas even if reverted | Charge only on success |
| **Required token** | Must hold ETH for gas | Stablecoins only (USD) |
| **Finality** | Probabilistic (wait for confirmations) | Immediate — no reorgs |
| **Consensus** | Global ordering (all nodes agree on block) | Per-shard Raft consensus |
| **Propagation** | Broadcast blocks to all nodes | Direct writes to relevant shards |
| **`eth_gasPrice`** | Returns market rate | Fixed gas price (~986M wei, ~1 gwei) |
| **`eth_maxPriorityFeePerGas`** | Suggested priority fee | Always `0x0` |
| **`eth_getBalance`** | Native balance only | Native + convertible USD |
| **`eth_blockNumber`** | Monotonic block height | Current timestamp in milliseconds |
| **Block hash** | Hash of block header | Equals block number (timestamp-based) |
| **`transactionIndex`** | Position in block | Can be `0` for multiple txs in same ms |
| **`eth_syncing`** | Sync status object or false | Always `false` |
| **`eth_mining`** | Whether node is mining | Always `true` (agents always accept txs) |
| **`net_listening`** | Whether listening for peers | Always `false` (no P2P networking) |
| **`net_peerCount`** | Connected peers | Always `0x0` |

---

## Stablecoin-Native Fees (Turnstile)

### How it works

Radius enables users to pay gas fees directly in stablecoins (USD) rather than requiring a separate native gas token. This is called the **Turnstile mechanism** and it works automatically — no special code, configuration, or wallet changes required.

When you submit a transaction:

1. **Automatic detection** — Radius detects when a user lacks sufficient native tokens to pay gas
2. **USD conversion** — If the user holds enough stablecoins (USD), Radius converts just enough to provide the necessary native tokens
3. **Single transaction** — The conversion happens seamlessly within the same transaction execution
4. **No extra charges** — Users are not charged gas for the conversion process itself

### When conversion activates

Both conditions must be met:

1. User's native token balance is insufficient to cover the transaction's gas cost
2. User's USD balance is sufficient to generate the required native tokens

If either condition isn't met, the transaction fails with insufficient funds.

### Pricing

| Metric | Value |
|--------|-------|
| **Avg. stablecoin transfer cost** | ~0.0001 USD |
| **Gas price** | 9.85998816e-10 RUSD per gas (~986M wei) |
| **Gas used (avg. transfer)** | 101,444 |
| **Transactions per 1 USD** | ~100,000 |

### Transaction cost API

Fetch current fee data programmatically:

- **Testnet:** `https://testnet.radiustech.xyz/api/v1/network/transaction-cost`
- **Mainnet:** `https://network.radiustech.xyz/api/v1/network/transaction-cost`

Response fields: `cost_usd` (number), `gas_price_wei` (hex string), `gas_used` (number), `last_updated` (ms timestamp).

### Developer impact

As a developer building on Radius, **you don't need to do anything special**:

- **No API changes** — Standard Ethereum RPC calls work exactly as expected
- **No contract modifications** — Your smart contracts don't need updates
- **Transparent to users** — Users get the benefit automatically
- **Improved UX** — Users can transact with just stablecoins, reducing onboarding friction

### RPC behavior with Turnstile

**`eth_sendRawTransaction`** — If the user lacks native tokens but has sufficient SBC, the conversion executes automatically. The transaction state is committed, including any SBC conversions. Receipt logs include stablecoin conversion events.

**`eth_call` and `eth_estimateGas`** — Results assume Turnstile is available. If a user would lack native tokens, the simulation assumes the conversion happens. You get accurate estimates even if the user's wallet only contains stablecoins. If `from` is omitted or set to the zero address, gas-payment checks are skipped during dry-run execution.

**`eth_getBalance`** — Returns native tokens the user currently holds **plus** the native token equivalent of their convertible stablecoins. This ensures wallets like MetaMask accurately represent what users can spend.

**`rad_getBalanceRaw`** — Use this Radius-specific method when you need the raw RUSD balance without Turnstile-aware conversion logic.

Turnstile converts in `0.1`-unit increments. One minimum conversion (`0.1 SBC` to `0.1 RUSD`) covers about 10,000 standard SBC transfers. Turnstile execution gas is not charged to the caller.

### Example scenario

**User's wallet:**
- Native tokens: 0
- Stablecoins (USD): 10 USD

**What happens when user submits a transaction:**
1. Radius detects zero native tokens
2. Converts the required USD to native tokens
3. Transaction executes with the converted native tokens
4. Gas is paid, transaction completes

**User experience:** No wallet switching, no bridging, no swapping. Transaction sent and confirmed in one step.

---

## Faster Finality

| Ethereum | Radius |
|----------|--------|
| ~12 minutes for high confidence | Sub-second (~500ms) |
| 12+ confirmations recommended | 0 confirmations needed |
| Reorgs possible | No reorgs |

### Practical implications

On Ethereum, you typically wait for multiple block confirmations before considering a transaction final. On Radius, once `waitForTransactionReceipt` returns, the transaction is **permanently finalized**. There is no possibility of reorg.

This means:
- You can show "confirmed" UI immediately after receipt
- No need for confirmation progress bars
- Server-side verification can trust a single receipt
- Payment flows are near-instant from the user's perspective

```typescript
const hash = await walletClient.sendTransaction({
  to: recipient,
  value: parseEther('1.0'),
});

// This returns in ~500ms and the transaction is FINAL
const receipt = await publicClient.waitForTransactionReceipt({ hash });

if (receipt.status === 'success') {
  // Safe to unlock content, grant access, record payment, etc.
  // No need to wait for additional confirmations
}
```

---

## Solidity Patterns to Watch

### What works unchanged

```solidity
// Standard ERC-20 interactions — work fine
IERC20(token).transfer(recipient, amount);

// Storage operations — work fine
mapping(address => uint256) balances;
balances[msg.sender] = 100;

// Events — work fine
emit Transfer(from, to, amount);

// All OpenZeppelin contracts — work fine
// All standard precompiles (0x01 - 0x0a) — work fine
```

### What to avoid

```solidity
// DON'T — native balance behaves differently on Radius
require(address(this).balance > 0);

// DO — use ERC-20 balance checks instead
require(IERC20(feeToken).balanceOf(address(this)) > 0);
```

Because Radius is stablecoin-native, design payment flows around ERC-20 transfers rather than native ETH `payable` functions. Using `msg.value` and `payable` still works technically, but ERC-20-based flows are the idiomatic Radius pattern.

**Important:** SBC uses **6 decimals** (not 18). RUSD (native token) uses 18 decimals. Always use `parseUnits(amount, 6)` for SBC and `parseEther(amount)` for RUSD native transfers.

### Recommended payment pattern

```solidity
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract RadiusPayment {
    using SafeERC20 for IERC20;

    // radUSD token on Radius Testnet
    IERC20 public immutable paymentToken;

    constructor(address _paymentToken) {
        paymentToken = IERC20(_paymentToken);
    }

    function pay(uint256 amount) external {
        paymentToken.safeTransferFrom(msg.sender, address(this), amount);
        // Process payment...
    }
}
```

---

## Architecture Overview

### No blocks, no mining

Traditional blockchains batch transactions into blocks for consensus and propagation. Radius eliminates these constraints:

| Aspect | Blockchain | Radius |
|--------|-----------|--------|
| Consensus | Global (all nodes agree on block) | Per-shard (Raft replication) |
| Ordering | Sequential (one block at a time) | Parallel (independent shards) |
| Propagation | Broadcast blocks to all nodes | Direct writes to relevant shards |
| Finality | Probabilistic (wait for confirmations) | Immediate |

### Sharded state with parallel execution

Radius distributes state elements across multiple independent shard clusters. Each shard:

- Runs as a 3-node Raft cluster (tolerates 1 node failure)
- Stores a partition of the global state
- Processes transactions independently of other shards

This enables linear scalability:

| Shards | Keyspace per shard | Throughput |
|--------|-------------------|------------|
| 1 | 100% | 1x |
| 2 | 50% each | ~2x |
| 4 | 25% each | ~4x |
| N | 1/N each | ~Nx |

The system supports up to **16.7 million shards** (24-bit shard indexing).

### Performance numbers

| Metric | Value |
|--------|-------|
| **Throughput** | 2.8M+ TPS (tested, linearly scalable) |
| **Finality** | ~500ms |
| **Transaction cost** | ~0.0001 USD |
| **Finality model** | Deterministic after one Raft commit |

These are demonstrated capabilities under load testing, not theoretical limits. Throughput scales linearly by adding shard clusters.

### Per-shard consensus

Instead of global consensus on a block of transactions, Radius achieves consensus per-shard using Raft. This means:

- No mining or proof-of-work
- No validator coordination overhead
- No block production delays
- Immediate finality once Raft commits

### Data integrity

Radius uses operator trust + replication rather than decentralized consensus:

- 3-node clusters provide fault tolerance
- Cryptographic signing prevents tampering
- Deterministic execution ensures consistency

This trade-off (known operators for instant finality) is appropriate for payment infrastructure.

### Congestion control

When multiple transactions compete for the same key, Radius uses intelligent batching:

1. **Detection** — Shards track which keys cause conflicts
2. **Routing** — Frontend routes conflicting transactions to the same backend
3. **Batching** — Backend executes conflicting transactions sequentially within a single batch
4. **Efficiency** — One lock acquisition serves the entire batch

### Specialized shards

| Shard Type | Purpose | Use Case |
|-----------|---------|----------|
| **Regular** | General state storage | Default workloads |
| **Receipt** | Transaction receipts | Append-heavy, read-light |
| **Edge** | Specific contracts/keys | High-traffic contracts |

Edge shards allow routing high-traffic contracts to dedicated infrastructure without affecting the rest of the system.

---

## EIP Support (Osaka Hardfork)

Radius tracks the Osaka hardfork via Revm 33.1.0:

| EIP | Description |
|-----|------------|
| EIP-7702 | Set EOA account code |
| EIP-1559 | Fee market (adapted for stablecoins) |
| EIP-2930 | Access lists |
| EIP-4844 | Blob transactions |

## Precompiles

All standard precompiles plus Radius extensions:

| Address | Precompile |
|---------|-----------|
| `0x01` - `0x0a` | Standard Ethereum precompiles |
| `0x4Db27Fa...` | Radius Edge (external data) |
| `0x07a2bA2...` | Debug utilities |

---

## RPC Behavioral Differences

### Methods that return different values

| Method | Ethereum | Radius |
|--------|----------|--------|
| `eth_gasPrice` | Market-driven gas price | Fixed gas price (~986M wei) |
| `eth_maxPriorityFeePerGas` | Suggested priority fee | `0x0` |
| `eth_getBalance` | Native balance only | Native + convertible USD |
| `eth_mining` | Mining status | Always `true` |
| `eth_syncing` | Sync progress or `false` | Always `false` |
| `eth_hashrate` | Current hashrate | `0x0` |
| `net_listening` | Peer listening status | `false` |
| `net_peerCount` | Number of peers | `0x0` |
| `eth_accounts` | Managed accounts | Empty array `[]` |
| `eth_feeHistory` | Historical fee data | Pseudo-supported (stablecoin fees) |

### Methods that are pseudo-supported

**`eth_getBlockByHash`** — Radius does not index blocks by hash in the traditional sense.

**`eth_feeHistory`** — Returns data, but Radius uses stablecoin fees rather than dynamic gas pricing.

**`eth_uninstallFilter`** — Radius does not persist filters. Always returns `true`.

### Radius-specific methods

**`rad_getBalanceRaw`** — Raw RUSD balance without Turnstile-aware conversion logic.

**`dash_globalGasUsage`** — Total gas usage across the system (returns floating-point number).

**`dash_globalTps`** — Current transactions per second across the system.

**`dash_latestTransactions`** — Most recent transactions (pass count as parameter).

**`dash_findTransactionsByAddress`** — Transactions involving a specific address.

**`rad_decodeKey`** — Decode a hashed key by monitoring broker operations.

**`trace_call`** — Execute a call and retrieve detailed trace information (Parity-compatible).

---

## FAQ

**Do I need to change my Solidity code?**
No. Your contracts deploy and run unchanged. The only thing to be mindful of is using ERC-20 balance checks instead of native balance patterns.

**Will my frontend work?**
Yes. wagmi, viem — all standard Ethereum libraries work with Radius. Use viem directly (no wrapper SDK needed).

**Do I need to handle gas price differently?**
For most cases, no — standard gas estimation works. However, for the most reliable behavior, define `fees.estimateFeesPerGas()` in your chain config and fetch `gas_price_wei` from the transaction cost API. This avoids edge cases where tooling derives incorrect fee values.

**What about block confirmations?**
You don't need them. Once `waitForTransactionReceipt` returns with `status: 'success'`, the transaction is final. No reorgs are possible.

**Is there MEV on Radius?**
No traditional MEV. Radius uses per-shard consensus without a global mempool, eliminating the block-builder extraction patterns common on Ethereum.

**Can I use Hardhat instead of Foundry?**
Foundry is recommended. Hardhat should work since Radius exposes a standard JSON-RPC interface, but Foundry is the tested and documented toolchain.