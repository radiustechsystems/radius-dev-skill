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

The skill previously stated `eth_gasPrice` returns `0x0`. This is **wrong**.

- `eth_gasPrice` returns the fixed gas price (~986M wei, ~1 gwei).
- `eth_maxPriorityFeePerGas` returns `0x0` (no priority fee bidding).

Always use the transaction cost API for the most reliable value:

```typescript
async function fetchGasPrice(): Promise<bigint> {
  try {
    const res = await fetch(
      'https://testnet.radiustech.xyz/api/v1/network/transaction-cost'
    );
    const data = await res.json();
    const price = BigInt(data.gas_price_wei);
    return price > 0n ? price : 986000000n;
  } catch {
    return 986000000n; // ~1 gwei fallback
  }
}
```

Define `fees.estimateFeesPerGas()` in your chain config. If tooling derives zero or invalid fee values, transactions fail silently.

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
    params: [{ chainId: '0x2D3' }], // 723 mainnet
  });
} catch (switchError) {
  const code = switchError.code ?? switchError.data?.originalError?.code;
  if (code === 4902 || code === -32603) {
    // Chain not recognized — attempt to add it
    await provider.request({
      method: 'wallet_addEthereumChain',
      params: [{
        chainId: '0x2D3',
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

- MetaMask: hex string `"0x2D3"`
- Some wallets: decimal string `"723"`
- Some wallets: number `723`

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

The SBC token uses EIP-2612 permits. The EIP-712 domain must match what the token contract was deployed with:

```typescript
const domain = {
  name: 'SBC',          // NOT "SBC Token", NOT "Radius SBC"
  version: '1',         // String "1", not number 1
  chainId: 723,         // Actual chain ID as a number
  verifyingContract: '0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb',
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

## 10. Nonce reading — "pending" block tag may not work

To read the current nonce for a permit, fall back from `"pending"` to `"latest"`:

```typescript
async function readNonce(
  publicClient: PublicClient,
  tokenAddress: Address,
  owner: Address
): Promise<string> {
  const data = '0x7ecebe00' + owner.slice(2).padStart(64, '0');

  for (const blockTag of ['pending', 'latest'] as const) {
    try {
      const result = await publicClient.request({
        method: 'eth_call',
        params: [{ to: tokenAddress, data }, blockTag],
      });
      return BigInt(result).toString();
    } catch (err) {
      if (blockTag === 'latest') throw err;
    }
  }
  throw new Error('Failed to read nonce');
}
```

---

## 11. EIP-1559 fee estimation can fail — force legacy `gasPrice`

On Radius, EIP-1559 RPC signals can look valid but still lead clients to build invalid fee values:

- `eth_gasPrice` returns ~`1 gwei` (usable)
- `eth_maxPriorityFeePerGas` can return `0x0`
- `eth_feeHistory` returns `baseFeePerGas`

In this state, viem's EIP-1559 estimator may produce `maxFeePerGas: 0`, and the RPC rejects the transaction with `"Specified gas price is too low"`.

Use an explicit legacy fee instead: fetch `gasPrice` and pass it directly in writes. This forces a type-0 transaction and bypasses broken EIP-1559 estimation.

```typescript
const gasPrice = await publicClient.getGasPrice();

const hash = await walletClient.sendTransaction({
    account,
    to,
    value,
    data,
    gasPrice, // <- explicit
});
```

Important: don't pass EIP-1559 fee fields (`maxFeePerGas` and `maxPriorityFeePerGas`) when using `gasPrice` — they will be ignored.

---

## 12. Settlement uses permit + transferFrom (two transactions)

The x402 flow uses two-step on-chain settlement:

1. `permit(owner, spender, value, deadline, v, r, s)` — sets allowance
2. `transferFrom(owner, paymentAddress, value)` — moves tokens

Both are sent from the settlement wallet. This means:
- The settlement wallet needs RUSD for gas.
- The settlement wallet's address is the `spender` in the permit.
- The `paymentAddress` (token recipient) can differ from the settlement wallet.

---

## 13. CORS — proxy RPC calls through your backend

The Radius RPC and Explorer API should be called from your server, not directly from the browser. Set up a thin proxy layer for browser-based apps.

---

## 14. Explorer API base path is `/api`

The Radius Explorer REST API is served under `/api`:

```
https://network.radiustech.xyz/api/v1/transactions/latest?limit=50
```

Not at the root path. This is not prominently documented.

---

## 15. EIP-6963 wallet discovery timing

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

## 16. Extract revert reasons from wrapped errors

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

## 17. Initialize chain stats before server listen

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

## 18. nodejs_compat to the CF Workers

Using viem server-side in Cloudflare Workers requires compatibility_flags = ["nodejs_compat"] in wrangler.toml. Without it, the Worker fails silently at deploy time or crashes at runtime.


## Quick reference: environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RADIUS_RPC_API_KEY` | Yes (production) | API key for authenticated RPC access |
| `SETTLEMENT_PRIVATE_KEY` | Yes (x402) | Private key for the settlement wallet (needs RUSD for gas) |
| `SBC_ASSET` | No | SBC token address (default: `0x33ad...14fb`) |
| `PAYMENT_ADDRESS` | No | Token recipient address |
| `NETWORK_CHAIN_ID` | No | Chain ID (default: 723 for mainnet, 72344 for testnet) |
