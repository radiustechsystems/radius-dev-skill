# Micropayment Patterns

## Overview

Radius enables micropayment business models that are impossible on traditional payment rails. With transaction costs of ~0.0001 USD and instant finality, you can charge per article, per API call, or per second of compute — profitably.

This document covers three core micropayment patterns:
1. **Pay-per-visit content** — Users pay cents per article instead of monthly subscriptions
2. **Real-time API metering** — Per-request billing with on-chain payment proof
3. **Streaming payments** — Continuous per-second billing for compute, bandwidth, and content

---

## Pay-per-Visit Content

### The problem

Traditional content monetization forces painful trade-offs:

- **Subscriptions** force users to pay for content they don't consume. Most readers abandon paywalls rather than commit monthly for a single article.
- **Ads** damage user experience, raise privacy concerns, and generate little revenue per user.
- **Freemium models** leave money on the table from engaged users willing to pay.

Radius solves this with **pay-per-visit micropayments** — users pay exactly for what they read, watch, or download. No subscriptions. No trackers. Instant access.

### How it works

1. **User lands on premium content** and sees a paywall with the price
2. **Clicks "Unlock"** and confirms a micropayment in their wallet (MetaMask, etc.)
3. **Client sends the transaction hash to your server** for verification
4. **Server verifies the payment on-chain** (checks status, amount, and recipient)
5. **Server records the payment and returns the premium content** — content is never sent to the client until payment is verified
6. **On repeat visits**, the server checks existing payment records and serves content immediately

Radius handles the heavy lifting: gas fees are paid in stablecoins via Turnstile, transactions settle in seconds, and there's no intermediary taking a cut.

> **⚠️ Security:** Premium content must be delivered by the server only after payment verification. Never gate content client-side with a boolean flag — it can be trivially bypassed via browser devtools. See [security.md](security.md): *"Payment verification happens server-side, not client-side."*

### Implementation: Paywall component

The paywall component does **not** receive premium content as `children`. Content lives on your server and is delivered only after payment is verified server-side.

```typescript
import { useState, useEffect } from 'react';
import { parseEther } from 'viem';
import { useAccount, useSendTransaction, useWaitForTransactionReceipt } from 'wagmi';

interface ContentPaywallProps {
  contentId: string;
  title: string;
  amount: string; // e.g., "0.10" (USD)
  contentOwner: string; // Payment recipient address
  preview?: React.ReactNode; // Optional teaser (safe to show before payment)
}

export function ContentPaywall({
  contentId,
  title,
  amount,
  contentOwner,
  preview,
}: ContentPaywallProps) {
  const { address, isConnected } = useAccount();
  const [unlockedContent, setUnlockedContent] = useState<string | null>(null);
  const [isPaying, setIsPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: hash, sendTransaction, isPending } = useSendTransaction();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({
    hash,
  });

  // On mount: check if this user already paid (repeat visit)
  useEffect(() => {
    if (!address) return;
    fetch(`/api/content/${contentId}/access?address=${address}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.content) setUnlockedContent(data.content);
      })
      .catch(() => {}); // No existing access — show paywall
  }, [address, contentId]);

  // After payment confirms on-chain, verify server-side and fetch content
  useEffect(() => {
    if (!isSuccess || !hash || !address || unlockedContent) return;

    fetch('/api/content/verify-payment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        transactionHash: hash,
        contentId,
        userAddress: address,
      }),
    })
      .then((res) => {
        if (!res.ok) throw new Error('Payment verification failed');
        return res.json();
      })
      .then((data) => {
        if (data.content) {
          setUnlockedContent(data.content);
        } else {
          setError('Payment verified but content unavailable');
        }
        setIsPaying(false);
      })
      .catch((err) => {
        setError(err.message);
        setIsPaying(false);
      });
  }, [isSuccess, hash, address, contentId, unlockedContent]);

  const handleUnlock = async () => {
    if (!address) return;
    setIsPaying(true);
    setError(null);

    try {
      sendTransaction({
        to: contentOwner as `0x${string}`,
        value: parseEther(amount),
      });
    } catch (err) {
      console.error('Payment failed:', err);
      setIsPaying(false);
    }
  };

  if (!isConnected) {
    return (
      <div className="paywall">
        <h2>{title}</h2>
        <p>Connect your wallet to unlock this content.</p>
      </div>
    );
  }

  // Content delivered by the server after verification — safe to render
  if (unlockedContent) {
    return (
      <div className="content">
        <h2>{title}</h2>
        <div>{unlockedContent}</div>
      </div>
    );
  }

  return (
    <div className="paywall">
      <h2>{title}</h2>
      {preview && <div className="preview">{preview}</div>}
      <p>
        This premium content costs <strong>{amount} USD</strong> to unlock.
      </p>
      <p>One-time payment. No subscription. Instant access.</p>

      {error && <p className="error">{error}</p>}

      <button
        onClick={handleUnlock}
        disabled={isPaying || isConfirming}
        className="unlock-button"
      >
        {isPaying || isConfirming ? 'Processing...' : `Unlock for ${amount} USD`}
      </button>

      {isPending && <p className="status">Awaiting wallet confirmation...</p>}
      {isConfirming && <p className="status">Confirming payment...</p>}
      {hash && (
        <p className="transaction-hash">
          Transaction: {hash.slice(0, 10)}...{hash.slice(-8)}
        </p>
      )}
    </div>
  );
}
```

### Usage

```typescript
export default function ArticlePage() {
  return (
    <ContentPaywall
      contentId="article-123"
      title="The Future of Micropayments"
      amount="0.10"
      contentOwner="0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1"
      preview={<p>Micropayments enable creators to monetize directly...</p>}
    />
  );
}
```

Note: premium content is **not** passed as `children`. It lives on your server and is delivered only after payment verification. The optional `preview` prop is for safe-to-show teasers.

### Server: payment verification and content delivery

The server is the security boundary. It verifies on-chain payment, records it, and delivers content. Premium content is never exposed to unauthenticated requests.

**POST `/api/content/verify-payment`** — Verify a new payment and return content:

```typescript
import { createPublicClient, http, parseEther, defineChain } from 'viem';

// Define Radius Testnet (see typescript-viem.md for the full chain definition)
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

// Helper: look up the expected price for a content item
function getContentPrice(contentId: string): string {
  // In production, fetch from your database or config
  const prices: Record<string, string> = {
    'article-123': '0.10',
    'video-456': '0.25',
  };
  return prices[contentId] ?? '0.10';
}

export default async function handler(req, res) {
  const { transactionHash, contentId, userAddress } = req.body;

  try {
    // Check for replay — reject if this tx hash was already used
    const existing = await db.payments.findOne({ transactionHash });
    if (existing) {
      if (existing.userAddress === userAddress && existing.contentId === contentId) {
        const content = await db.content.findById(contentId);
        return res.status(200).json({ verified: true, content: content.body });
      }
      return res.status(400).json({ error: 'Transaction already used' });
    }

    // Verify transaction on-chain
    const receipt = await publicClient.getTransactionReceipt({
      hash: transactionHash,
    });

    if (receipt.status !== 'success') {
      return res.status(400).json({ error: 'Payment transaction failed' });
    }

    // Verify amount
    const tx = await publicClient.getTransaction({ hash: transactionHash });
    const expectedAmount = parseEther(getContentPrice(contentId));

    if (tx.value < expectedAmount) {
      return res.status(400).json({ error: 'Incorrect payment amount' });
    }

    // Record successful payment
    await db.payments.create({
      contentId,
      userAddress,
      transactionHash,
      amount: tx.value.toString(),
      timestamp: new Date(),
    });

    // Return content — this is the gate
    const content = await db.content.findById(contentId);
    return res.status(200).json({ verified: true, content: content.body });
  } catch (error) {
    console.error('Verification error:', error);
    return res.status(500).json({ error: 'Verification failed' });
  }
}
```

**GET `/api/content/:id/access`** — Check existing access for repeat visits:

```typescript
// GET /api/content/:id/access?address=0x...
export default async function handler(req, res) {
  const { id } = req.query;
  const { address } = req.query;

  if (!id || !address) {
    return res.status(400).json({ error: 'Missing contentId or address' });
  }

  const payment = await db.payments.findOne({
    contentId: id,
    userAddress: address,
  });

  if (!payment) {
    return res.status(403).json({ hasAccess: false });
  }

  const content = await db.content.findById(id);
  return res.status(200).json({ hasAccess: true, content: content.body });
}
```

### Multiple price tiers

```typescript
const contentTiers: Record<string, string> = {
  article: '0.05',   // 0.05 USD per article
  video: '0.25',     // 0.25 USD per video
  research: '1.00',  // 1.00 USD per research paper
  masterclass: '5.00', // 5.00 USD per masterclass
};

export function ContentLibrary() {
  const items = [
    { id: '1', title: 'Breaking News', type: 'article' },
    { id: '2', title: 'Tutorial: viem on Radius', type: 'video' },
    { id: '3', title: 'Stablecoin Economics', type: 'research' },
  ];

  return (
    <div>
      {items.map((item) => (
        <ContentPaywall
          key={item.id}
          contentId={item.id}
          title={item.title}
          amount={contentTiers[item.type]}
          contentOwner="0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1"
        />
      ))}
    </div>
  );
}
```

### Benefits

**For users:**
- Lower barrier than subscriptions — pay 0.10 USD for one article instead of 15 USD/month
- No tracking required — stablecoins provide value; ads and trackers don't
- Global access — pay with stablecoins from any country; instant settlement
- Instant access — content unlocks immediately after payment

**For creators:**
- Higher effective revenue — every engaged reader becomes a paying user
- No chargeback risk — stablecoin transactions are final
- Direct payment — money goes directly to you; no platform taking 30%
- Flexible pricing — set different prices for articles, videos, research

### Content use cases

- **News & Journalism** — Articles, investigations, breaking news
- **Video Content** — Tutorials, documentaries, educational videos
- **Research & Data** — Academic papers, market research, whitepapers
- **Premium Tutorials** — In-depth guides, programming courses
- **Podcasts** — Individual episode access or full-library unlock
- **Photography & Art** — High-resolution downloads, exclusive collections
- **Gaming Content** — Cosmetics, level packs, exclusive streams
- **Expert Advice** — Consultations, AMA sessions, email support tiers

### Get started

#### 1. Install dependencies

```bash
pnpm add wagmi viem @tanstack/react-query
```

#### 2. Configure wagmi

```typescript
import { WagmiProvider, createConfig, http } from 'wagmi';
import { defineChain } from 'viem';
import { injected } from 'wagmi/connectors';

// Define Radius Testnet (see typescript-viem.md for the full chain definition)
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

const config = createConfig({
  chains: [radiusTestnet],
  connectors: [injected()],
  transports: {
    [radiusTestnet.id]: http(),
  },
});

export function App({ children }) {
  return <WagmiProvider config={config}>{children}</WagmiProvider>;
}
```

#### 3. Wrap your app

```typescript
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient();

export default function RootApp() {
  return (
    <QueryClientProvider client={queryClient}>
      <App>
        <YourContent />
      </App>
    </QueryClientProvider>
  );
}
```

#### 4. Deploy and test

Test with Radius Testnet before going live. Get free test tokens from the faucet: https://testnet.radiustech.xyz/testnet/faucet

### Best practices

1. **Never gate content client-side** — Always deliver premium content from the server after payment verification. A client-side `isUnlocked` flag is trivially bypassed via browser devtools
2. **Show the price upfront** — Users hate surprises. Display the cost before they click "unlock"
3. **Make wallet connection obvious** — If not connected, guide users to connect before payment
4. **Handle network errors gracefully** — Show retry buttons if payment fails
5. **Store payment receipts** — Keep transaction hashes for support, analytics, and replay protection
6. **Check for replay** — Reject transaction hashes that have already been used for a different user or content item
7. **Offer value for the price** — 0.10 USD articles should be substantial; avoid paywalling single paragraphs
8. **Test on testnet first** — Always verify payment flow before production
9. **Monitor gas costs** — Radius fees are low, but still track transaction costs

### Scaling considerations

- **Batch settlements** — Collect multiple payments, settle once daily to save costs
- **Tiered content** — Use content length/quality to justify different price points
- **Bundle offers** — Sell article packs ("10 articles for 0.50 USD") to increase AOV
- **Incentivize loyalty** — Offer discounts to frequent readers or newsletter subscribers
- **Track conversion** — Monitor which price points convert best for different content types

---

## Real-time API Metering

### The problem

Traditional API billing relies on monthly invoices with credit card processing — a system plagued with friction. API providers wait 30+ days to see revenue, pay 2.9% + 0.30 USD per transaction in processor fees, and face chargebacks. Users in developing regions often can't pay by credit card at all.

Radius solves this with **real-time, per-request billing**. Each API call includes payment that settles instantly on-chain. No credit card fees. No chargebacks. No intermediaries.

### How it works

1. **Client sends payment** — Constructs a micro-transaction on Radius and gets a transaction hash
2. **Client calls API with payment proof** — Includes the transaction hash in the request
3. **Server verifies payment** — Verifies the payment on Radius in milliseconds
4. **Request executes** — If payment is valid, your API processes the request
5. **Instant settlement** — Payment is finalized within seconds

Total latency: sub-second verification + your API response time.

### Server implementation

Create an Express.js API that charges per request:

```typescript
import express, { Request, Response } from 'express';
import { createPublicClient, createWalletClient, http, parseEther, isAddress, defineChain } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import type { Address, Hash } from 'viem';

// Define Radius Testnet (see typescript-viem.md for the full chain definition)
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

// Server account (receives payments)
const serverAccount = privateKeyToAccount(
  process.env.SERVER_PRIVATE_KEY as `0x${string}`
);

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const walletClient = createWalletClient({
  account: serverAccount,
  chain: radiusTestnet,
  transport: http(),
});

// Pricing
const COST_PER_REQUEST = parseEther('0.001'); // 0.001 USD per request

const app = express();
app.use(express.json());

/**
 * Verify that a payment transaction was sent to the server
 */
async function verifyPayment(
  transactionHash: Hash,
  expectedAmount: bigint,
  expectedRecipient: Address
): Promise<Address | null> {
  try {
    const receipt = await publicClient.waitForTransactionReceipt({
      hash: transactionHash,
    });

    if (receipt.status !== 'success') {
      return null;
    }

    const tx = await publicClient.getTransaction({
      hash: transactionHash,
    });

    if (
      !tx.to ||
      tx.to.toLowerCase() !== expectedRecipient.toLowerCase() ||
      tx.value < expectedAmount
    ) {
      return null;
    }

    return tx.from;
  } catch (error) {
    console.error('Payment verification failed:', error);
    return null;
  }
}

/**
 * Protected API endpoint that requires payment
 */
app.post('/api/query', async (req: Request, res: Response) => {
  const { paymentHash, query } = req.body;

  if (!paymentHash || !query) {
    return res.status(400).json({
      error: 'Missing paymentHash or query',
    });
  }

  const payer = await verifyPayment(
    paymentHash as Hash,
    COST_PER_REQUEST,
    serverAccount.address
  );

  if (!payer) {
    return res.status(402).json({
      error: 'Payment verification failed or insufficient amount',
    });
  }

  console.log(`Query from ${payer}: ${query}`);

  const result = {
    query,
    result: `Processing query: "${query}"`,
    processedAt: new Date().toISOString(),
    paidBy: payer,
  };

  return res.json({ success: true, data: result });
});

/**
 * Health check (no payment required)
 */
app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok', serverAddress: serverAccount.address });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`API server running on http://localhost:${PORT}`);
  console.log(`Server receives payments at: ${serverAccount.address}`);
});
```

### Client implementation

```typescript
import { createPublicClient, createWalletClient, http, parseEther, defineChain } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import type { Address } from 'viem';

// Use the same radiusTestnet chain definition from the server implementation above

const apiServerUrl = 'http://localhost:3000';
const serverAddress: Address = process.env.SERVER_ADDRESS as `0x${string}`;
const clientPrivateKey = process.env.CLIENT_PRIVATE_KEY as `0x${string}`;

const clientAccount = privateKeyToAccount(clientPrivateKey);

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const walletClient = createWalletClient({
  account: clientAccount,
  chain: radiusTestnet,
  transport: http(),
});

const COST_PER_REQUEST = parseEther('0.001');

/**
 * Make a metered API call:
 * 1. Send payment to the server
 * 2. Use the transaction hash as proof of payment
 * 3. Call the API with the payment proof
 */
async function callMeteredAPI(query: string): Promise<void> {
  console.log(`\nCalling API with query: "${query}"`);

  // Step 1: Send payment
  console.log('Sending payment...');
  const paymentHash = await walletClient.sendTransaction({
    to: serverAddress,
    value: COST_PER_REQUEST,
  });

  console.log(`Payment sent: ${paymentHash}`);

  // Step 2: Call the API with payment proof
  console.log('Calling API endpoint...');
  const response = await fetch(`${apiServerUrl}/api/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paymentHash, query }),
  });

  if (!response.ok) {
    const error = await response.json();
    console.error(`API error (${response.status}):`, error);
    return;
  }

  const result = await response.json();
  console.log('API response:', result.data);
}

// Example usage
async function main() {
  try {
    const balance = await publicClient.getBalance({
      address: clientAccount.address,
    });
    console.log(`Client balance: ${balance.toString()} wei`);

    await callMeteredAPI('What is 2 + 2?');
    await callMeteredAPI('What is the capital of France?');
  } catch (error) {
    console.error('Error:', error);
  }
}

main();
```

### Running the example

Create `.env`:

```bash
# Server wallet (receives payments)
SERVER_PRIVATE_KEY=0x...

# Client wallet (sends payments)
CLIENT_PRIVATE_KEY=0x...

# For client: server's address (where to send payments)
SERVER_ADDRESS=0x...
```

Get testnet tokens from the [Radius Faucet](https://testnet.radiustech.xyz/testnet/faucet) for both wallets.

```bash
# Terminal 1: Start server
node --env-file=.env --import=tsx api-server.ts

# Terminal 2: Run client
node --env-file=.env --import=tsx api-client.ts
```

### Pricing strategies

```typescript
// Fixed rate per request
const COST_PER_REQUEST = parseEther('0.001');

// Tiered pricing based on request type
const PRICING = {
  basic: parseEther('0.001'),
  premium: parseEther('0.005'),
  enterprise: parseEther('0.01'),
};

// Per-token pricing for AI/ML APIs
const COST_PER_TOKEN = parseEther('0.000001');
```

### Production considerations

- **Nonce tracking** — Store processed transaction hashes to prevent replay attacks
- **Timeout handling** — If a transaction takes too long to finalize, retry or fail gracefully
- **Rate limiting** — Limit requests per wallet to prevent spam
- **Amount validation** — Verify the payment amount exactly matches your pricing
- **Monitoring** — Track payment success rates and processing times

### Benefits vs. traditional API billing

| Feature | Traditional | Radius |
|---------|------------|--------|
| **Payment fees** | 2.9% + 0.30 USD | ~0.000001 USD per transfer |
| **Settlement time** | 30+ days | Seconds |
| **Chargebacks** | Common, costly | Impossible (on-chain) |
| **Global access** | Credit card required | Wallet + USD only |
| **Minimum transaction** | 5-10 USD | 0.0001 USD |
| **Revenue control** | Intermediary takes a cut | You control 100% |

### API metering use cases

**AI/ML APIs** — Charge per inference or per token:

```typescript
const costPerToken = parseEther('0.000001');
const tokensGenerated = 150;
const totalCost = BigInt(tokensGenerated) * costPerToken;

const hash = await walletClient.sendTransaction({
  to: apiServer,
  value: totalCost,
});
```

**Premium data feeds** — Real-time stock prices, weather data, sports stats.

**Content APIs** — Charge for access to paywalled articles, ebooks, or videos:

```typescript
const contentId = '123-article-slug';
const hash = await walletClient.sendTransaction({
  to: publisherAddress,
  value: ARTICLE_COST,
});

const content = await fetch('/api/articles/' + contentId, {
  headers: { 'X-Payment-Hash': hash },
});
```

---

## Streaming Payments

### The problem

Traditional billing models create friction for continuous services:

- **Upfront payment risk** — Users pre-pay without knowing exact consumption, risking overpayment
- **Invoice-based delays** — Providers wait days or weeks to get paid, exposing themselves to default risk
- **Coarse billing granularity** — Services charge by month or hour, forcing users to pay for unused capacity

Radius solves this with **continuous micropayments** — pay-as-you-consume settlement at second-level granularity, eliminating both payment and credit risk.

### How it works

1. **Client initiates a session** with the server, providing an account with available funds
2. **Payments flow at regular intervals** (every second, every minute) based on service consumption
3. **Service continues uninterrupted** as long as payments arrive on schedule
4. **Either party can terminate** anytime — the client stops payments, or the server stops service

This creates a natural "circuit breaker": if the client runs out of funds or the server detects payment failure, service halts immediately.

### Client: payment stream loop

```typescript
import { createPublicClient, createWalletClient, http, parseEther, defineChain } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';

// Define Radius Testnet (see typescript-viem.md for the full chain definition)
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

const account = privateKeyToAccount(
  process.env.RADIUS_PRIVATE_KEY as `0x${string}`
);

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const walletClient = createWalletClient({
  account,
  chain: radiusTestnet,
  transport: http(),
});

const SERVICE_ADDRESS = '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1' as const;
const PAYMENT_INTERVAL_MS = 1000;           // Pay every 1 second
const PAYMENT_AMOUNT = parseEther('0.001'); // 0.001 USD per second

let isStreamActive = true;
let totalPaid = 0n;

async function startPaymentStream() {
  console.log('Starting payment stream to:', SERVICE_ADDRESS);

  const balance = await publicClient.getBalance({ address: account.address });
  console.log('Starting balance:', balance.toString(), 'wei');

  const intervalId = setInterval(async () => {
    if (!isStreamActive) {
      clearInterval(intervalId);
      console.log('Payment stream stopped. Total paid:', totalPaid.toString());
      return;
    }

    try {
      const hash = await walletClient.sendTransaction({
        to: SERVICE_ADDRESS,
        value: PAYMENT_AMOUNT,
      });

      const receipt = await publicClient.waitForTransactionReceipt({ hash });

      if (receipt.status === 'success') {
        totalPaid += PAYMENT_AMOUNT;
        console.log(
          `Payment sent: ${PAYMENT_AMOUNT.toString()} wei (Total: ${totalPaid.toString()})`
        );
      } else {
        console.error('Payment reverted:', hash);
        isStreamActive = false;
      }
    } catch (error) {
      console.error('Payment error:', error);
      isStreamActive = false;
    }
  }, PAYMENT_INTERVAL_MS);

  return intervalId;
}

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down payment stream...');
  isStreamActive = false;
  process.exit(0);
});

startPaymentStream();
```

### Server: session manager

```typescript
import { createPublicClient, http, defineChain } from 'viem';
import type { Address } from 'viem';

// Use the same radiusTestnet chain definition from the client implementation above

interface PaymentSession {
  clientAddress: Address;
  startTime: number;
  lastPaymentTime: number;
  amountReceived: bigint;
  isActive: boolean;
}

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const PAYMENT_TIMEOUT_MS = 5000; // Terminate if no payment for 5 seconds
const sessions = new Map<Address, PaymentSession>();

/**
 * Monitor sessions and terminate on payment timeout
 */
function monitorPayments() {
  setInterval(() => {
    const now = Date.now();

    sessions.forEach((session, clientAddress) => {
      const timeSinceLastPayment = now - session.lastPaymentTime;

      if (timeSinceLastPayment > PAYMENT_TIMEOUT_MS && session.isActive) {
        console.log(`Terminating session: Payment timeout for ${clientAddress}`);
        session.isActive = false;
        terminateSession(clientAddress);
      }
    });
  }, 1000);
}

/**
 * Handle an incoming payment from a client
 */
function handleIncomingPayment(
  clientAddress: Address,
  amount: bigint,
  timestamp: number
) {
  let session = sessions.get(clientAddress);

  if (!session) {
    session = {
      clientAddress,
      startTime: timestamp,
      lastPaymentTime: timestamp,
      amountReceived: amount,
      isActive: true,
    };
    sessions.set(clientAddress, session);
    console.log(`New session created: ${clientAddress}`);
  } else {
    session.lastPaymentTime = timestamp;
    session.amountReceived += amount;
    console.log(
      `Payment received from ${clientAddress}: ${amount.toString()} wei (Total: ${session.amountReceived.toString()})`
    );
  }

  return session;
}

/**
 * Terminate a session and clean up resources
 */
function terminateSession(clientAddress: Address) {
  const session = sessions.get(clientAddress);
  if (session) {
    const duration = Date.now() - session.startTime;
    console.log(`Session ended: ${clientAddress}`);
    console.log(`  Duration: ${duration}ms`);
    console.log(`  Total received: ${session.amountReceived.toString()} wei`);
    sessions.delete(clientAddress);
  }
}

/**
 * Get active sessions (for monitoring/admin)
 */
function getActiveSessions() {
  return Array.from(sessions.values()).filter((s) => s.isActive);
}

monitorPayments();

export {
  handleIncomingPayment,
  terminateSession,
  getActiveSessions,
  type PaymentSession,
};
```

### Graceful termination on payment failure

```typescript
async function streamWithFallback(
  serviceAddress: Address,
  paymentAmount: bigint,
  maxRetries: number = 3
) {
  let retries = 0;

  const intervalId = setInterval(async () => {
    try {
      const hash = await walletClient.sendTransaction({
        to: serviceAddress,
        value: paymentAmount,
      });
      await publicClient.waitForTransactionReceipt({ hash });
      retries = 0; // Reset on success
      console.log('Payment successful');
    } catch (error) {
      retries++;
      console.warn(`Payment failed (attempt ${retries}/${maxRetries}):`, error);

      if (retries >= maxRetries) {
        clearInterval(intervalId);
        console.error('Max retries exceeded. Terminating session.');
        process.exit(1);
      }
    }
  }, 1000);

  return intervalId;
}
```

### Session duration tracking

```typescript
interface StreamingSession {
  serviceAddress: Address;
  startTime: Date;
  totalSpent: bigint;
  isActive: boolean;
}

async function createStreamingSession(
  serviceAddress: Address,
  budgetPerSecond: bigint
): Promise<StreamingSession> {
  const session: StreamingSession = {
    serviceAddress,
    startTime: new Date(),
    totalSpent: 0n,
    isActive: true,
  };

  const intervalId = setInterval(async () => {
    if (!session.isActive) {
      clearInterval(intervalId);
      const duration = new Date().getTime() - session.startTime.getTime();
      console.log(
        `Session ended after ${duration}ms. Total spent: ${session.totalSpent.toString()}`
      );
      return;
    }

    try {
      const hash = await walletClient.sendTransaction({
        to: serviceAddress,
        value: budgetPerSecond,
      });
      await publicClient.waitForTransactionReceipt({ hash });
      session.totalSpent += budgetPerSecond;
    } catch (error) {
      session.isActive = false;
      console.error('Session terminated due to payment error:', error);
    }
  }, 1000);

  return session;
}

// Usage — stop after 30 seconds
const session = await createStreamingSession(
  '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1',
  parseEther('0.0001')
);

setTimeout(() => {
  session.isActive = false;
}, 30000);
```

### Benefits of streaming payments

| Benefit | Impact |
|---------|--------|
| **No overpayment** | Pay only for what you consume, down to the second |
| **No credit risk** | Real-time settlement eliminates provider default risk |
| **Granular billing** | Per-second pricing enables precise cost-matching |
| **Instant termination** | Service stops immediately on payment failure |
| **Predictable costs** | Linear per-unit pricing with no hidden fees |
| **Improved UX** | Users pay gradually instead of large upfront amounts |

### Streaming payment use cases

**Cloud compute** — Pay-per-second VMs and container instances. Example: 0.0001 USD per second per vCPU.

**Video/content streaming** — Pay-per-minute or per-gigabyte. Example: 0.00001 USD per MB of video data.

**WiFi and network access** — Pay-per-minute connectivity. Example: 0.0001 USD per minute of active connection.

**AI inference and APIs** — Pay-per-token or per-request. Example: 0.00001 USD per 1,000 tokens generated.

### Best practices for streaming payments

#### 1. Balance checks

Always verify sufficient balance before starting a stream:

```typescript
const balance = await publicClient.getBalance({ address: account.address });
const requiredBalance = paymentPerSecond * BigInt(durationSeconds);

if (balance < requiredBalance) {
  throw new Error('Insufficient balance for requested stream duration');
}
```

#### 2. Payment intervals

Choose intervals based on service needs:

| Interval | Use case | Trade-off |
|----------|----------|-----------|
| **1 second** | Fine-grained billing | Higher gas cost per unit time |
| **5-10 seconds** | Balanced approach for most services | Good default choice |
| **30-60 seconds** | Lower cost, coarser billing | Acceptable for less time-sensitive services |

#### 3. Error handling

Implement robust fallback logic:

```typescript
const maxRetries = 3;
let failureCount = 0;

try {
  const hash = await walletClient.sendTransaction({
    to: serviceAddress,
    value: amount,
  });
  await publicClient.waitForTransactionReceipt({ hash });
  failureCount = 0; // Reset on success
} catch (error) {
  failureCount++;
  if (failureCount >= maxRetries) {
    // Terminate session
  }
}
```

#### 4. Session monitoring

Track session health and detect hung payments:

```typescript
let lastPaymentTime = Date.now();
const TIMEOUT_MS = 10000;

setInterval(() => {
  if (Date.now() - lastPaymentTime > TIMEOUT_MS) {
    console.error('Payment timeout detected');
    stopStream();
  }
}, 1000);
```

---

## Network configuration for micropayments

| Setting | Value |
|---------|-------|
| **RPC Endpoint** | `https://rpc.testnet.radiustech.xyz` |
| **Chain ID** | `72344` |
| **Native Token** | RUSD |
| **Block time** | ~2-3 seconds |
| **Transaction cost** | ~0.0001 USD |
| **Faucet** | `https://testnet.radiustech.xyz/testnet/faucet` |

Testnet is perfect for experimenting with all micropayment patterns. Get free RUSD tokens from the faucet to start building.