# x402 Client-Side Implementation

This reference provides everything needed to consume x402-protected APIs — sign payment permits and send them with your requests.

**Only dependency:** `viem`

---

## Why two signatures?

x402 on Radius uses a **dual-signature** Permit2 flow. The client never sends a transaction — it signs two EIP-712 typed data messages:

1. **EIP-2612 permit** — tells the SBC token contract: "I approve the Permit2 contract to spend X amount of my SBC." The spender is the **Permit2 contract** (`0x0000...8BA3`).

2. **Permit2 PermitWitnessTransferFrom** — tells the Permit2 contract: "I authorize the x402 Proxy to transfer X SBC from me to the payment recipient." The spender is the **x402 Proxy** (`0x4020...0001`).

The facilitator receives both signatures and executes them on-chain in a single settlement transaction.

---

## EIP-712 typed data structures

### EIP-2612 Permit (signature 1)

```typescript
const permitDomain = {
  name: 'Stable Coin',
  version: '1',
  chainId: 723487,                // or 72344 for testnet
  verifyingContract: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb', // SBC token
};

const permitTypes = {
  Permit: [
    { name: 'owner', type: 'address' },
    { name: 'spender', type: 'address' },
    { name: 'value', type: 'uint256' },
    { name: 'nonce', type: 'uint256' },
    { name: 'deadline', type: 'uint256' },
  ],
};

// Message values:
// owner     = your wallet address
// spender   = Permit2 contract: 0x000000000022D473030F116dDEE9F6B43aC78BA3
// value     = payment amount in raw 6-decimal units (e.g. 100n for 0.0001 SBC)
// nonce     = read from SBC contract: nonces(ownerAddress) — sequential, starts at 0
// deadline  = Unix timestamp (e.g. now + 300 seconds)
```

### Permit2 PermitWitnessTransferFrom (signature 2)

```typescript
const permit2Domain = {
  name: 'Permit2',
  chainId: 723487,                // or 72344 for testnet
  verifyingContract: '0x000000000022D473030F116dDEE9F6B43aC78BA3', // Permit2 contract
};

const permit2Types = {
  PermitWitnessTransferFrom: [
    { name: 'permitted', type: 'TokenPermissions' },
    { name: 'spender', type: 'address' },
    { name: 'nonce', type: 'uint256' },
    { name: 'deadline', type: 'uint256' },
    { name: 'witness', type: 'Witness' },
  ],
  TokenPermissions: [
    { name: 'token', type: 'address' },
    { name: 'amount', type: 'uint256' },
  ],
  Witness: [
    { name: 'to', type: 'address' },
    { name: 'validAfter', type: 'uint256' },
  ],
};

// Message values:
// permitted.token  = SBC address: 0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb
// permitted.amount = payment amount (same as EIP-2612 value)
// spender          = x402 Proxy: 0x402085c248EeA27D92E8b30b2C58ed07f9E20001
// nonce            = random (crypto random bytes, NOT sequential)
// deadline         = Unix timestamp (same as EIP-2612 deadline)
// witness.to       = payTo address (the merchant receiving payment)
// witness.validAfter = 0 (no earliest-valid constraint)
```

---

## signX402Payment function

```typescript
import { type Hex } from 'viem';

const RADIUS_DEFAULTS = {
  chainId: 723487,
  tokenAddress: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb' as `0x${string}`,
  tokenName: 'Stable Coin',
  tokenVersion: '1',
  permit2Address: '0x000000000022D473030F116dDEE9F6B43aC78BA3' as `0x${string}`,
  x402Permit2Proxy: '0x402085c248EeA27D92E8b30b2C58ed07f9E20001' as `0x${string}`,
};

function randomPermit2Nonce(): bigint {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return BigInt('0x' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join(''));
}

interface SignX402Params {
  /** EIP-712 signTypedData function (from viem account or browser wallet) */
  signTypedData: (params: any) => Promise<Hex>;
  /** Payer wallet address */
  owner: `0x${string}`;
  /** EIP-2612 nonce — read from SBC contract: nonces(ownerAddress) */
  permitNonce: bigint;
  /** The resource being paid for */
  resource: { url: string; description?: string; mimeType?: string };
  /** Payment requirements from the server's 402 response */
  accepted: {
    scheme: string;
    network: string;
    amount: string;
    asset: string;
    payTo: string;
    maxTimeoutSeconds: number;
    extra: { name: string; version: string; assetTransferMethod: string };
  };
  /** Optional overrides for chain defaults */
  config?: Partial<typeof RADIUS_DEFAULTS>;
}

export async function signX402Payment({
  signTypedData,
  owner,
  permitNonce,
  resource,
  accepted,
  config,
}: SignX402Params): Promise<{ payload: any; xPayment: string }> {
  const cfg = { ...RADIUS_DEFAULTS, ...config };
  const deadline = BigInt(Math.floor(Date.now() / 1000) + 300);
  const amount = accepted.amount;

  // 1. Sign EIP-2612 permit (approve Permit2 contract to spend SBC)
  const eip2612Signature = await signTypedData({
    domain: {
      name: cfg.tokenName,
      version: cfg.tokenVersion,
      chainId: cfg.chainId,
      verifyingContract: cfg.tokenAddress,
    },
    types: {
      Permit: [
        { name: 'owner', type: 'address' },
        { name: 'spender', type: 'address' },
        { name: 'value', type: 'uint256' },
        { name: 'nonce', type: 'uint256' },
        { name: 'deadline', type: 'uint256' },
      ],
    },
    primaryType: 'Permit' as const,
    message: {
      owner,
      spender: cfg.permit2Address,
      value: BigInt(amount),
      nonce: permitNonce,
      deadline,
    },
  });

  // 2. Sign Permit2 PermitWitnessTransferFrom (authorize token transfer via x402 Proxy)
  const p2Nonce = randomPermit2Nonce();
  const permit2Signature = await signTypedData({
    domain: {
      name: 'Permit2',
      chainId: cfg.chainId,
      verifyingContract: cfg.permit2Address,
    },
    types: {
      PermitWitnessTransferFrom: [
        { name: 'permitted', type: 'TokenPermissions' },
        { name: 'spender', type: 'address' },
        { name: 'nonce', type: 'uint256' },
        { name: 'deadline', type: 'uint256' },
        { name: 'witness', type: 'Witness' },
      ],
      TokenPermissions: [
        { name: 'token', type: 'address' },
        { name: 'amount', type: 'uint256' },
      ],
      Witness: [
        { name: 'to', type: 'address' },
        { name: 'validAfter', type: 'uint256' },
      ],
    },
    primaryType: 'PermitWitnessTransferFrom' as const,
    message: {
      permitted: { token: cfg.tokenAddress, amount: BigInt(amount) },
      spender: cfg.x402Permit2Proxy,
      nonce: p2Nonce,
      deadline,
      witness: { to: accepted.payTo as `0x${string}`, validAfter: 0n },
    },
  });

  // 3. Build the full payload
  const payload = {
    x402Version: 2,
    scheme: 'exact',
    network: `eip155:${cfg.chainId}`,
    resource: {
      url: resource.url,
      description: resource.description ?? '',
      mimeType: resource.mimeType ?? 'application/json',
    },
    accepted,
    payload: {
      signature: permit2Signature,
      permit2Authorization: {
        permitted: { token: cfg.tokenAddress, amount: amount.toString() },
        from: owner,
        spender: cfg.x402Permit2Proxy,
        nonce: p2Nonce.toString(),
        deadline: deadline.toString(),
        witness: { to: accepted.payTo, validAfter: '0' },
      },
    },
    extensions: {
      eip2612GasSponsoring: {
        info: {
          amount: amount.toString(),
          deadline: deadline.toString(),
          signature: eip2612Signature,
        },
      },
    },
  };

  return { payload, xPayment: btoa(JSON.stringify(payload)) };
}
```

---

## Reading the EIP-2612 nonce

The EIP-2612 permit nonce is **sequential** — read it from the SBC token contract before signing.

```typescript
import { createPublicClient, http, parseAbi, defineChain } from 'viem';

// See radius-dev skill for full chain definition
const radiusMainnet = defineChain({
  id: 723487,
  name: 'Radius Network',
  nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
  rpcUrls: { default: { http: ['https://rpc.radiustech.xyz'] } },
});

const SBC_ADDRESS = '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb' as const;

const publicClient = createPublicClient({
  chain: radiusMainnet,
  transport: http(),
});

async function getPermitNonce(owner: `0x${string}`): Promise<bigint> {
  return publicClient.readContract({
    address: SBC_ADDRESS,
    abi: parseAbi(['function nonces(address owner) view returns (uint256)']),
    functionName: 'nonces',
    args: [owner],
  });
}
```

---

## Example: Node.js script consuming a paid API

> Include `signX402Payment`, `RADIUS_DEFAULTS`, and `randomPermit2Nonce` from the section above.

```typescript
import { createPublicClient, http, parseAbi } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { defineChain } from 'viem';

// Chain definition (see radius-dev skill)
const radiusMainnet = defineChain({
  id: 723487,
  name: 'Radius Network',
  nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
  rpcUrls: { default: { http: ['https://rpc.radiustech.xyz'] } },
  blockExplorers: {
    default: { name: 'Radius Explorer', url: 'https://network.radiustech.xyz' },
  },
});

const SBC_ADDRESS = '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb' as const;

const account = privateKeyToAccount(process.env.PRIVATE_KEY as `0x${string}`);
const publicClient = createPublicClient({ chain: radiusMainnet, transport: http() });

async function callPaidApi(apiUrl: string) {
  // 1. Request without payment — get 402 + requirements
  const initialRes = await fetch(apiUrl);
  if (initialRes.status !== 402) {
    console.log('No payment required:', await initialRes.json());
    return;
  }

  const requirements = await initialRes.json();
  const accepted = requirements.paymentRequirements[0];

  // 2. Read EIP-2612 nonce
  const permitNonce = await publicClient.readContract({
    address: SBC_ADDRESS,
    abi: parseAbi(['function nonces(address) view returns (uint256)']),
    functionName: 'nonces',
    args: [account.address],
  });

  // 3. Sign payment
  const { xPayment } = await signX402Payment({
    signTypedData: (params) => account.signTypedData(params),
    owner: account.address,
    permitNonce,
    resource: { url: apiUrl, description: `Access to ${new URL(apiUrl).pathname}` },
    accepted,
  });

  // 4. Retry with payment
  const paidRes = await fetch(apiUrl, {
    headers: { 'X-Payment': xPayment },
  });

  console.log('Status:', paidRes.status);
  console.log('Data:', await paidRes.json());
}

callPaidApi('https://your-x402-api.example.com/api/data');
```

---

## Example: Browser wallet (wagmi/viem)

> Include `signX402Payment`, `RADIUS_DEFAULTS`, and `randomPermit2Nonce` from the section above.

```typescript
import { useAccount, useWalletClient } from 'wagmi';
import { createPublicClient, http, parseAbi } from 'viem';

const SBC_ADDRESS = '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb' as const;

export function usePaidFetch() {
  const { address } = useAccount();
  const { data: walletClient } = useWalletClient();

  async function fetchWithPayment(apiUrl: string) {
    if (!address || !walletClient) throw new Error('Wallet not connected');

    // 1. Get 402 requirements
    const initialRes = await fetch(apiUrl);
    if (initialRes.status !== 402) return initialRes.json();
    const requirements = await initialRes.json();
    const accepted = requirements.paymentRequirements[0];

    // 2. Read EIP-2612 nonce
    const publicClient = createPublicClient({
      chain: walletClient.chain,
      transport: http(),
    });
    const permitNonce = await publicClient.readContract({
      address: SBC_ADDRESS as `0x${string}`,
      abi: parseAbi(['function nonces(address) view returns (uint256)']),
      functionName: 'nonces',
      args: [address],
    });

    // 3. Sign payment (browser wallet popup for each signature)
    const { xPayment } = await signX402Payment({
      signTypedData: (params: any) => walletClient.signTypedData(params),
      owner: address,
      permitNonce,
      resource: { url: apiUrl },
      accepted,
    });

    // 4. Retry with payment
    const paidRes = await fetch(apiUrl, {
      headers: { 'X-Payment': xPayment },
    });
    return paidRes.json();
  }

  return { fetchWithPayment };
}
```

---

## Error handling

### Parsing 402 responses

```typescript
async function parsePaymentRequirements(response: Response) {
  if (response.status !== 402) return null;

  const body = await response.json();

  // Validate x402 v2 format
  if (body.x402Version !== 2 || !body.paymentRequirements?.length) {
    throw new Error('Unexpected 402 response format');
  }

  return body.paymentRequirements[0];
}
```

### Handling payment failures

After sending the `X-Payment` header, the server may still return non-200:

| Status | Meaning | Action |
|--------|---------|--------|
| 200 | Payment accepted | Parse response body as normal |
| 400 | Malformed X-Payment header | Check base64 encoding, JSON structure |
| 402 | Payment verification failed | Requirements may have changed — re-fetch 402 and re-sign |
| 502 | Facilitator unavailable | Retry after a short delay |

```typescript
// Uses signX402Payment, getPermitNonce, and account from sections above.
async function fetchWithRetry(apiUrl: string, maxRetries = 2) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const res = await fetch(apiUrl);
    if (res.status !== 402) return res;

    const accepted = (await res.json()).paymentRequirements[0];
    const permitNonce = await getPermitNonce(account.address);

    const { xPayment } = await signX402Payment({
      signTypedData: (params) => account.signTypedData(params),
      owner: account.address,
      permitNonce,
      resource: { url: apiUrl },
      accepted,
    });

    const paidRes = await fetch(apiUrl, { headers: { 'X-Payment': xPayment } });
    if (paidRes.ok) return paidRes;

    // If still 402, requirements may have changed — loop and re-sign
    if (paidRes.status === 402 && attempt < maxRetries) continue;
    return paidRes;
  }
}
```

---

## Testnet: pre-approving Permit2 for FareSide

The FareSide facilitator (`facilitator.x402.rs`) does **not** process EIP-2612 gas sponsoring during settlement. Fresh wallets must pre-approve the Permit2 contract before their first x402 payment on testnet.

Use EIP-2612 `permit()` on the SBC contract to grant Permit2 an allowance:

```typescript
import { createPublicClient, createWalletClient, http, parseAbi, maxUint256, defineChain } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';

const radiusTestnet = defineChain({
  id: 72344,
  name: 'Radius Testnet',
  nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
  rpcUrls: { default: { http: ['https://rpc.testnet.radiustech.xyz'] } },
});

const SBC_ADDRESS = '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb' as const;
const PERMIT2_ADDRESS = '0x000000000022D473030F116dDEE9F6B43aC78BA3' as const;

const account = privateKeyToAccount(process.env.PRIVATE_KEY as `0x${string}`);
const publicClient = createPublicClient({ chain: radiusTestnet, transport: http() });
const walletClient = createWalletClient({ chain: radiusTestnet, transport: http(), account });

async function approvePermit2ForTestnet() {
  // Read current nonce
  const nonce = await publicClient.readContract({
    address: SBC_ADDRESS,
    abi: parseAbi(['function nonces(address) view returns (uint256)']),
    functionName: 'nonces',
    args: [account.address],
  });

  // Sign EIP-2612 permit granting Permit2 a large allowance
  const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600); // 1 hour
  const value = maxUint256; // max allowance

  const signature = await account.signTypedData({
    domain: {
      name: 'Stable Coin',
      version: '1',
      chainId: 72344,
      verifyingContract: SBC_ADDRESS,
    },
    types: {
      Permit: [
        { name: 'owner', type: 'address' },
        { name: 'spender', type: 'address' },
        { name: 'value', type: 'uint256' },
        { name: 'nonce', type: 'uint256' },
        { name: 'deadline', type: 'uint256' },
      ],
    },
    primaryType: 'Permit',
    message: {
      owner: account.address,
      spender: PERMIT2_ADDRESS,
      value,
      nonce,
      deadline,
    },
  });

  // Split signature for on-chain permit call
  const r = `0x${signature.slice(2, 66)}` as `0x${string}`;
  const s = `0x${signature.slice(66, 130)}` as `0x${string}`;
  let v = parseInt(signature.slice(130, 132), 16);
  if (v < 27) v += 27;

  // Submit permit transaction
  const hash = await walletClient.writeContract({
    address: SBC_ADDRESS,
    abi: parseAbi([
      'function permit(address owner, address spender, uint256 value, uint256 deadline, uint8 v, bytes32 r, bytes32 s)',
    ]),
    functionName: 'permit',
    args: [account.address, PERMIT2_ADDRESS, value, deadline, v, r, s],
  });

  const receipt = await publicClient.waitForTransactionReceipt({ hash });
  console.log('Permit2 approved:', receipt.status, 'tx:', hash);
}

approvePermit2ForTestnet();
```

> **This is only needed for testnet with FareSide.** On mainnet, `facilitator.andrs.dev` handles
> gas sponsoring automatically — no pre-approval required.

---

## Discovering x402 services

x402 facilitators and registries that implement the `/discovery/resources` convention serve a machine-readable catalog of available services. This is the primary way agents discover paywalled APIs programmatically.

### Known discovery endpoints

| Provider | URL | Scope |
|----------|-----|-------|
| Coinbase CDP | `https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources` | Cross-chain (Base, Solana, more) |
| PayAI | `https://facilitator.payai.network/discovery/resources` | Cross-chain |

### Response format

Each endpoint returns a JSON object with an `items` array. Each item describes one paywalled service:

```typescript
interface DiscoveryResponse {
  items: {
    /** The paywalled endpoint URL */
    resource: string;
    /** Resource type (typically "http") */
    type: string;
    /** When the listing was last updated */
    lastUpdated: string;
    /** Payment options the service accepts */
    accepts: {
      /** Token contract address */
      asset: string;
      /** CAIP-2 network identifier (e.g. "eip155:723487" for Radius mainnet) */
      network: string;
      /** Price in raw token units */
      maxAmountRequired: string;
      /** Payment scheme (typically "exact") */
      scheme: string;
      /** Wallet receiving payment */
      payTo: string;
      /** Human-readable description of the service */
      description: string;
      /** Response content type */
      mimeType: string;
      /** Token metadata */
      extra: { name: string; version: string };
      /** Input/output schema for the endpoint (optional) */
      outputSchema?: object;
    }[];
  }[];
}
```

### Querying for Radius services

Filter discovery results by Radius network identifiers to find services on Radius:

```typescript
const RADIUS_NETWORKS = ['eip155:723487', 'eip155:72344'];

const DISCOVERY_ENDPOINTS = [
  'https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources',
  'https://facilitator.payai.network/discovery/resources',
];

async function discoverRadiusServices() {
  const services = [];

  for (const endpoint of DISCOVERY_ENDPOINTS) {
    try {
      const res = await fetch(endpoint);
      if (!res.ok) continue;
      const data = await res.json();

      for (const item of data.items ?? []) {
        const radiusAccepts = item.accepts?.filter(
          (a: any) => RADIUS_NETWORKS.includes(a.network),
        );
        if (radiusAccepts?.length) {
          services.push({
            url: item.resource,
            description: radiusAccepts[0].description,
            price: radiusAccepts[0].maxAmountRequired,
            network: radiusAccepts[0].network,
          });
        }
      }
    } catch {
      // Discovery endpoint unavailable — skip
    }
  }

  return services;
}
```

> **Discovery is additive.** As more facilitators and registries implement `/discovery/resources`,
> add their URLs to the `DISCOVERY_ENDPOINTS` array. The response format is standardized across
> providers.
