# Production Gotchas

Hard-won lessons from real-world Radius integrations. Review before shipping.

## 1. SBC uses 6 decimals, not 18

This is the single most common mistake. The SBC ERC-20 token on mainnet uses **6 decimals**. RUSD (native token) uses 18.

```typescript
import { parseUnits, formatUnits } from 'viem';

// CORRECT — SBC uses 6 decimals
const amount = parseUnits('1.0', 6);     // 1_000_000n
const display = formatUnits(balance, 6); // "1.000000"

// WRONG — sends 1e12x too much or displays balance as near-zero
const amount = parseUnits('1.0', 18);    // 1_000_000_000_000_000_000n
```

The authoritative docs confirm: "RUSD uses 18 decimals, while SBC uses 6. For SBC, `10^6` base units map to `10^18` base units of RUSD at the same face value."

---

## 2. Gas price is NOT zero

- `eth_gasPrice` returns the fixed gas price (~986M wei, ~1 gwei).
- `eth_maxPriorityFeePerGas` returns the actual gas price (same value as `eth_gasPrice`).

Query the gas price via `eth_gasPrice` RPC:

```typescript
const gasPrice = await publicClient.request({ method: 'eth_gasPrice' });
const price = BigInt(gasPrice); // ~986000000n (~1 gwei)
```

Both `eth_gasPrice` and `eth_maxPriorityFeePerGas` return the correct fixed price. Standard viem fee estimation works.

---

## 3. Wallet compatibility — MetaMask only (reliably)

Radius is a custom network. Most wallets don't know about it.

- **MetaMask**: Reliably adds and switches to Radius via `wallet_addEthereumChain`.
- **Coinbase Wallet, Trust Wallet, Rainbow**: May reject adding unknown chains entirely.

Handle both error codes when switching fails:

```typescript
try {
  await provider.request({
    method: 'wallet_switchEthereumChain',
    params: [{ chainId: '0xB0A1F' }], // 723487 mainnet
  });
} catch (switchError) {
  const code = switchError.code ?? switchError.data?.originalError?.code;
  if (code === 4902 || code === -32603) {
    // Chain not recognized — attempt to add it
    await provider.request({
      method: 'wallet_addEthereumChain',
      params: [{
        chainId: '0xB0A1F',
        chainName: 'Radius Network',
        nativeCurrency: { name: 'RUSD', symbol: 'RUSD', decimals: 18 },
        rpcUrls: ['https://rpc.radiustech.xyz'],
        blockExplorerUrls: ['https://network.radiustech.xyz'],
      }],
    });
  }
}
```

Show unsupported wallets as "Coming Soon" rather than letting users hit confusing errors.

---

## 4. Chain ID format varies between wallets

Different wallets return `eth_chainId` in different formats:

- MetaMask: hex string `"0xB0A1F"`
- Some wallets: decimal string `"723487"`
- Some wallets: number `723487`

Always normalize before comparing:

```typescript
function normalizeChainId(chainId: string | number): string {
  if (typeof chainId === 'number') return '0x' + chainId.toString(16);
  if (typeof chainId === 'string' && !chainId.startsWith('0x')) {
    return '0x' + parseInt(chainId, 10).toString(16);
  }
  return chainId;
}
```

---

## 5. Block numbers are timestamps — use BigInt

`eth_blockNumber` returns the current timestamp in **milliseconds** (hex encoded). These values are extremely large (~1.77 trillion range).

```typescript
// WRONG — loses precision at these magnitudes
const block = parseInt(hexBlockNumber, 16);

// CORRECT
const block = BigInt(hexBlockNumber);
```

Do not:
- Iterate blocks sequentially (enormous gaps between blocks with transactions).
- Treat block number as canonical chain height.
- Assume "N blocks later" semantics match Ethereum finality patterns.

---

## 6. Transaction receipts can be null

`eth_getTransactionReceipt` can return `null` even for confirmed transactions that appear in the Explorer API. Always handle this:

```typescript
const receipt = await publicClient.getTransactionReceipt({ hash });

if (!receipt) {
  // Transaction exists but receipt is unavailable
  // Fetch transaction directly and construct a fallback
  const tx = await publicClient.getTransaction({ hash });
  // Handle gracefully — don't crash
}
```

---

## 7. Nonce collisions under concurrent load

When sending multiple transactions from the same wallet (hot wallet, settlement wallet), concurrent sends cause nonce errors. Radius enforces strict sequential nonces.

**Solution: serial queue + nonce retry.**

```typescript
function isNonceError(err: any): boolean {
  const msg = (err?.message || err?.shortMessage || String(err)).toLowerCase();
  return msg.includes('nonce') ||
         msg.includes('replacement transaction underpriced') ||
         msg.includes('already known');
}

async function sendWithRetry(
  walletClient: WalletClient,
  publicClient: PublicClient,
  params: TransactionParams
): Promise<Hash> {
  try {
    return await walletClient.sendTransaction(params);
  } catch (err: any) {
    if (!isNonceError(err)) throw err;

    for (let attempt = 1; attempt <= 3; attempt++) {
      await new Promise(r => setTimeout(r, 500));
      const freshNonce = await publicClient.getTransactionCount({
        address: params.account,
      });
      try {
        return await walletClient.sendTransaction({ ...params, nonce: freshNonce });
      } catch (retryErr: any) {
        if (attempt === 3 || !isNonceError(retryErr)) throw retryErr;
      }
    }
    throw err;
  }
}
```

Also add a ~200ms delay between consecutive transactions. Without it, the RPC sometimes returns stale nonce values.

---

## 8. EIP-2612 permit signing — domain must match exactly

The Stable Coin token uses EIP-2612 permits. The EIP-712 domain must match what the token contract was deployed with:

```typescript
const domain = {
  name: 'Stable Coin',          // NOT "SBC", NOT "Radius SBC"
  version: '1',         // String "1", not number 1
  chainId: 723487,      // Actual chain ID as a number
  verifyingContract: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
};
```

If any field is wrong, `recoverTypedDataAddress` recovers a different address and the permit fails silently.

---

## 9. Signature v-value normalization

After `eth_signTypedData_v4`, the v value needs normalization:

```typescript
const r = '0x' + signature.slice(2, 66);
const s = '0x' + signature.slice(66, 130);
let v = parseInt(signature.slice(130, 132), 16);
if (v < 27) v += 27; // Ledger and some hardware wallets return 0 or 1
```

Without this, server-side signature recovery fails for hardware wallet users.

---

## 10. Nonce reading for permits

To read the current nonce for a permit:

```typescript
async function readNonce(
  publicClient: PublicClient,
  tokenAddress: Address,
  owner: Address
): Promise<string> {
  const data = '0x7ecebe00' + owner.slice(2).padStart(64, '0');
  const result = await publicClient.request({
    method: 'eth_call',
    params: [{ to: tokenAddress, data }, 'pending'],
  });
  return BigInt(result).toString();
}
```

---

## 11. Settlement uses permit + transferFrom (two transactions)

The x402 flow uses two-step on-chain settlement:

1. `permit(owner, spender, value, deadline, v, r, s)` — sets allowance
2. `transferFrom(owner, paymentAddress, value)` — moves tokens

Both are sent from the settlement wallet. This means:
- The settlement wallet needs RUSD for gas.
- The settlement wallet's address is the `spender` in the permit.
- The `paymentAddress` (token recipient) can differ from the settlement wallet.

---

## 12. CORS — proxy RPC calls through your backend

The Radius RPC and Explorer API should be called from your server, not directly from the browser. Set up a thin proxy layer for browser-based apps.

---

## 13. Explorer API base path is `/api`

The Radius Explorer REST API is served under `/api`:

```
https://network.radiustech.xyz/api/v1/transactions/latest?limit=50
```

Not at the root path. This is not prominently documented.

---

## 14. EIP-6963 wallet discovery timing

Modern multi-wallet setups fight over `window.ethereum`. Use EIP-6963:

```typescript
const wallets: Map<string, EIP6963ProviderDetail> = new Map();
let timer: ReturnType<typeof setTimeout>;

window.addEventListener('eip6963:announceProvider', (event) => {
  const { info, provider } = (event as CustomEvent).detail;
  if (typeof provider.request === 'function') {
    wallets.set(info.uuid, { info, provider });
  }
  clearTimeout(timer);
  timer = setTimeout(markReady, 500); // Reset — more wallets may arrive
});

window.dispatchEvent(new Event('eip6963:requestProvider'));
timer = setTimeout(markReady, 500);
```

Wait at least 500ms. Some wallets announce late.

---

## 15. Extract revert reasons from wrapped errors

Radius reverts are wrapped in multiple error layers:

```typescript
function extractRevertReason(err: any): string {
  if (err?.shortMessage) return err.shortMessage;
  if (err?.cause?.shortMessage) return err.cause.shortMessage;
  const msg = err?.message || String(err);
  const match = msg.match(/reverted with reason string '([^']+)'/);
  if (match) return `Reverted: ${match[1]}`;
  const match2 = msg.match(/execution reverted: (.+)/);
  if (match2) return match2[1];
  return msg.slice(0, 200);
}
```

---

## 16. Initialize chain stats before server listen

If your app displays on-chain stats on the landing page, fetch them before `httpServer.listen()`. Otherwise the first visitors see all zeros.

```typescript
await Promise.race([
  Promise.all([verifyContracts(), initChainStats()]),
  new Promise((_, reject) =>
    setTimeout(() => reject(new Error('Init timeout')), 120_000)
  ),
]).catch(err => console.warn(`Init warning: ${err.message}`));

httpServer.listen(port);
```

---

## 17. nodejs_compat to the CF Workers

Using viem server-side in Cloudflare Workers requires compatibility_flags = ["nodejs_compat"] in wrangler.toml. Without it, the Worker fails silently at deploy time or crashes at runtime.


## 18. `eth_getLogs` requires an address filter

Unlike Ethereum, Radius **requires** an `address` field on all `eth_getLogs` calls. Omitting it returns error `-33014`.

Additionally, the block range is capped at 1,000,000 units. Because block numbers are millisecond timestamps, this covers ~16 minutes 40 seconds (not ~1 million blocks). Exceeding this range returns error `-33002`.

```typescript
// WRONG — returns error -33014 on Radius
const logs = await publicClient.getLogs({
  fromBlock: startBlock,
  toBlock: endBlock,
});

// CORRECT — always include address
const logs = await publicClient.getLogs({
  address: contractAddress,
  fromBlock: startBlock,
  toBlock: endBlock,
});
```

For large time ranges, split into consecutive chunks of up to 1,000,000 block units.

---

## 19. `blockhash()` is predictable — NOT random

On Radius, `BLOCKHASH` returns a timestamp-derived value, not a cryptographic hash. `blockhash(block.number - 1)` returns the previous millisecond timestamp cast to `bytes32`.

Any contract using `blockhash()` as a randomness source is **exploitable** on Radius.

```solidity
// INSECURE on Radius — value is fully predictable
uint256 random = uint256(blockhash(block.number - 1));
uint256 winner = random % participants.length;

// USE INSTEAD — Chainlink VRF or off-chain oracle for randomness
```

Vulnerable patterns: lotteries, NFT trait generation, commit-reveal schemes hashing against `blockhash()`, gaming contracts with randomized outcomes.

---

## 20. Historical block numbers rejected; named tags return current state

State query methods (`eth_getBalance`, `eth_call`, `eth_getCode`, `eth_getStorageAt`, `eth_getTransactionCount`, `eth_estimateGas`) parse block tags as follows:

- **Accepted:** `latest`, `pending`, `safe`, `finalized` — all return current state.
- **Rejected:** Historical block numbers and `earliest` — return error `-32000`: `"required historical state unavailable, only 'latest', 'pending', 'safe', and 'finalized' are supported block tags"`.

Radius does not support archive mode or historical state access.

Implications:
- Foundry fork mode (`--fork-block-number`) cannot query past state.
- Debugging reverted transactions with `eth_call` at a past block is not available.
- Price oracles and analytics that query historical balances will get error `-32000`.

---

## 21. Chain ID migration (723 → 723487)

The Radius mainnet chain ID changed from `723` (`0x2D3`) to `723487` (`0xB0A1F`). The testnet chain ID (`72344`) is unchanged. This affects several areas:

- **EIP-712 signatures:** Off-chain typed-data signatures (EIP-2612 permits, meta-transactions) signed with `chainId: 723` will not verify. DApps must re-request signatures from users.
- **Wallet configurations:** Users who added Radius to MetaMask with chain ID `723` need to remove and re-add the network with `723487` (`0xB0A1F`).
- **Hardcoded chain IDs:** Any application logic that hardcodes `723`, `0x2D3`, or `"723"` for chain detection or switching must be updated.

Best practice: read chain ID dynamically from the connected provider rather than hardcoding it.

---

## Quick reference: environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RADIUS_RPC_API_KEY` | Yes (production) | API key for authenticated RPC access |
| `SETTLEMENT_PRIVATE_KEY` | Yes (x402) | Private key for the settlement wallet (needs RUSD for gas) |
| `SBC_ASSET` | No | SBC token address (default: `0x33ad...14fb`) |
| `PAYMENT_ADDRESS` | No | Token recipient address |
| `NETWORK_CHAIN_ID` | No | Chain ID (default: 723487 for mainnet, 72344 for testnet) |
