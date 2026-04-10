# x402 Server-Side Implementation

This reference provides everything needed to add x402 payment gating to any HTTP server. The core module is framework-agnostic — it takes a standard `Request` and returns a typed outcome that you map to your framework's response.

**Only dependency:** `viem` (for types only — the module itself uses only `fetch` and `atob`).

---

## Types

```typescript
/** Configuration for x402 payment gating. One per app. */
export interface X402Config {
  /** SBC token contract address */
  asset: string;
  /** CAIP-2 chain identifier (e.g. "eip155:723487") */
  network: string;
  /** Wallet address that receives payments */
  payTo: string;
  /** Facilitator service base URL */
  facilitatorUrl: string;
  /** Payment amount in raw token units (6 decimals: "100" = 0.0001 SBC) */
  amount: string;
  /** Optional API key for the facilitator */
  facilitatorApiKey?: string;
  /** ERC-2612 permit domain name (default: "Stable Coin") */
  tokenName?: string;
  /** ERC-2612 permit domain version (default: "1") */
  tokenVersion?: string;
  /** HTTP header carrying the payment (default: "X-Payment") */
  paymentHeader?: string;
}

/** A single payment requirement in the 402 response */
export interface PaymentRequirement {
  scheme: string;
  network: string;
  amount: string;
  asset: string;
  payTo: string;
  maxTimeoutSeconds: number;
  extra: {
    name: string;
    version: string;
    assetTransferMethod: string;
  };
}

/** The full 402 response body (x402 v2) */
export interface PaymentRequirementsResponse {
  paymentRequirements: PaymentRequirement[];
  x402Version: number;
}

/** Options for processPayment behavior */
export interface PaymentOptions {
  /** Skip the verify step, go straight to settle */
  skipVerify?: boolean;
  /** Fire-and-forget settle: return before settlement confirms */
  asyncSettle?: boolean;
}

/** Every possible outcome of processPayment */
export type PaymentOutcome =
  | { status: 'no-payment'; requirements: PaymentRequirementsResponse }
  | { status: 'invalid-header' }
  | { status: 'verify-failed'; detail: any }
  | { status: 'verify-unreachable'; detail: string }
  | { status: 'settle-failed'; detail: any }
  | { status: 'settle-unreachable'; detail: string }
  | { status: 'settled'; txHash: string | undefined; verifyMs: number; settleMs: number; totalMs: number }
  | { status: 'settle-pending'; verifyMs: number; totalMs: number };
```

---

## Core functions

### buildPaymentRequirements

Constructs the 402 response body telling clients what payment the server accepts.

```typescript
export function buildPaymentRequirements(config: X402Config): PaymentRequirementsResponse {
  return {
    paymentRequirements: [
      {
        scheme: 'exact',
        network: config.network,
        amount: config.amount,
        asset: config.asset,
        payTo: config.payTo,
        maxTimeoutSeconds: 300,
        extra: {
          name: config.tokenName ?? 'Stable Coin',
          version: config.tokenVersion ?? '1',
          assetTransferMethod: 'permit2',
        },
      },
    ],
    x402Version: 2,
  };
}
```

### processPayment

The core x402 flow. Call this for every protected route.

```typescript
export async function processPayment(
  config: X402Config,
  request: Request,
  options?: PaymentOptions,
  ctx?: { waitUntil: (p: Promise<any>) => void },
): Promise<PaymentOutcome> {
  const headerName = config.paymentHeader ?? 'X-Payment';
  const paymentHeader = request.headers.get(headerName);

  // No payment header → return requirements for 402 response
  if (!paymentHeader) {
    return { status: 'no-payment', requirements: buildPaymentRequirements(config) };
  }

  // Decode the base64-encoded payment payload.
  // This is the ENTIRE client payload (x402Version, scheme, resource, accepted, payload, extensions).
  // Send the full object to the facilitator as paymentPayload — not just the inner .payload field.
  let paymentPayload: any;
  try {
    paymentPayload = JSON.parse(atob(paymentHeader));
  } catch {
    return { status: 'invalid-header' };
  }

  // Build facilitator request
  const facilitatorHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (config.facilitatorApiKey) {
    facilitatorHeaders['X-API-Key'] = config.facilitatorApiKey;
  }

  const facilitatorBody = JSON.stringify({
    x402Version: 2,
    paymentPayload,
    paymentRequirements: buildPaymentRequirements(config).paymentRequirements[0],
  });

  const t0 = Date.now();
  let verifyMs = 0;

  // Verify with facilitator (unless skipVerify)
  if (!options?.skipVerify) {
    let verifyRes: Response;
    try {
      verifyRes = await fetch(`${config.facilitatorUrl}/verify`, {
        method: 'POST',
        headers: facilitatorHeaders,
        body: facilitatorBody,
      });
    } catch (e: any) {
      return { status: 'verify-unreachable', detail: e.message };
    }
    verifyMs = Date.now() - t0;

    const verifyData: any = await verifyRes.json();
    if (!verifyData.isValid) {
      return { status: 'verify-failed', detail: verifyData };
    }
  }

  // Async settle — fire-and-forget, return immediately
  if (options?.asyncSettle) {
    const settlePromise = fetch(`${config.facilitatorUrl}/settle`, {
      method: 'POST',
      headers: facilitatorHeaders,
      body: facilitatorBody,
    })
      .then((r) => r.json())
      .catch(() => {});

    if (ctx) ctx.waitUntil(settlePromise);
    return { status: 'settle-pending', verifyMs, totalMs: Date.now() - t0 };
  }

  // Synchronous settle — wait for on-chain confirmation
  const t1 = Date.now();
  let settleRes: Response;
  try {
    settleRes = await fetch(`${config.facilitatorUrl}/settle`, {
      method: 'POST',
      headers: facilitatorHeaders,
      body: facilitatorBody,
    });
  } catch (e: any) {
    return { status: 'settle-unreachable', detail: e.message };
  }
  const settleMs = Date.now() - t1;

  const settleData: any = await settleRes.json();
  if (!settleData.success) {
    return { status: 'settle-failed', detail: settleData };
  }

  // Facilitator may return tx hash under different field names
  const txHash =
    settleData.transaction ??
    settleData.txHash ??
    settleData.transactionHash ??
    settleData.hash;

  return { status: 'settled', txHash, verifyMs, settleMs, totalMs: Date.now() - t0 };
}
```

---

## Helpers

```typescript
/** CORS headers that include the payment header. */
export function corsHeaders(config?: Partial<X402Config>): Record<string, string> {
  const header = config?.paymentHeader ?? 'X-Payment';
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': `Content-Type, ${header}`,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  };
}

/** JSON response with CORS headers. */
export function jsonResponse(data: unknown, status = 200, config?: Partial<X402Config>): Response {
  return Response.json(data, {
    status,
    headers: { ...corsHeaders(config), 'Content-Type': 'application/json' },
  });
}
```

---

## Integration: handling all outcome states

After calling `processPayment()`, map every outcome to the correct HTTP response:

```typescript
async function handlePaidRequest(request: Request, config: X402Config): Promise<Response> {
  const url = new URL(request.url);
  const outcome = await processPayment(config, request);

  switch (outcome.status) {
    case 'no-payment':
      return jsonResponse(outcome.requirements, 402, config);

    case 'invalid-header':
      return jsonResponse({ error: 'Invalid X-Payment header' }, 400, config);

    case 'verify-failed':
      return jsonResponse(
        { error: 'Payment verification failed', detail: outcome.detail },
        402,
        config,
      );

    case 'verify-unreachable':
    case 'settle-unreachable':
      return jsonResponse(
        { error: 'Facilitator unavailable', detail: outcome.detail },
        502,
        config,
      );

    case 'settle-failed':
      return jsonResponse(
        { error: 'Settlement failed', detail: outcome.detail },
        502,
        config,
      );

    case 'settle-pending':
    case 'settled':
      // Payment accepted — return the paid content
      // Replace with your application logic:
      return jsonResponse({ message: 'Payment accepted', path: url.pathname }, 200, config);
  }
}
```

---

## Framework integration examples

### Cloudflare Worker

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const config: X402Config = {
      asset: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
      network: 'eip155:723487',
      payTo: env.PAYMENT_ADDRESS,
      facilitatorUrl: 'https://facilitator.andrs.dev',
      facilitatorApiKey: env.FACILITATOR_API_KEY,
      amount: '100',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders(config) });
    }

    return handlePaidRequest(request, config);
  },
};
```

### Express middleware

```typescript
import express from 'express';

const app = express();

const config: X402Config = {
  asset: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  network: 'eip155:723487',
  payTo: process.env.PAYMENT_ADDRESS!,
  facilitatorUrl: 'https://facilitator.andrs.dev',
  amount: '100',
};

// x402 middleware for protected routes
async function x402Gate(req: express.Request, res: express.Response, next: express.NextFunction) {
  // Convert Express request to standard Request for processPayment
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) {
    if (typeof value === 'string') headers.set(key, value);
  }
  const request = new Request(`${req.protocol}://${req.get('host')}${req.originalUrl}`, {
    method: req.method,
    headers,
  });

  const outcome = await processPayment(config, request);

  if (outcome.status === 'settled' || outcome.status === 'settle-pending') {
    next(); // Payment accepted — proceed to route handler
    return;
  }

  // Map outcome to HTTP response
  if (outcome.status === 'no-payment') {
    res.status(402).json(outcome.requirements);
  } else if (outcome.status === 'invalid-header') {
    res.status(400).json({ error: 'Invalid X-Payment header' });
  } else if (outcome.status === 'verify-failed' || outcome.status === 'settle-failed') {
    res.status(402).json({ error: 'Payment failed', detail: outcome.detail });
  } else {
    res.status(502).json({ error: 'Facilitator unavailable' });
  }
}

app.get('/api/data', x402Gate, (req, res) => {
  res.json({ data: 'your protected content here' });
});
```

### Node.js http

```typescript
import { createServer } from 'node:http';

const config: X402Config = {
  asset: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  network: 'eip155:723487',
  payTo: process.env.PAYMENT_ADDRESS!,
  facilitatorUrl: 'https://facilitator.andrs.dev',
  amount: '100',
};

createServer(async (req, res) => {
  const url = new URL(req.url!, `http://${req.headers.host}`);
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) {
    if (typeof value === 'string') headers.set(key, value);
  }
  const request = new Request(url.toString(), { method: req.method!, headers });

  const outcome = await processPayment(config, request);

  res.setHeader('Content-Type', 'application/json');
  if (outcome.status === 'no-payment') {
    res.writeHead(402);
    res.end(JSON.stringify(outcome.requirements));
  } else if (outcome.status === 'settled' || outcome.status === 'settle-pending') {
    res.writeHead(200);
    res.end(JSON.stringify({ data: 'your protected content' }));
  } else {
    res.writeHead(outcome.status === 'invalid-header' ? 400 : 502);
    res.end(JSON.stringify({ error: outcome.status }));
  }
}).listen(3000);
```

---

## Multiple routes with different prices

```typescript
const ROUTE_PRICES: Record<string, string> = {
  '/api/basic':   '100',    // 0.0001 SBC
  '/api/premium': '10000',  // 0.01 SBC
  '/api/bulk':    '100000', // 0.1 SBC
};

async function handleRequest(request: Request, baseConfig: X402Config): Promise<Response> {
  const url = new URL(request.url);
  const price = ROUTE_PRICES[url.pathname];

  if (!price) {
    return jsonResponse({ error: 'Not found' }, 404);
  }

  const config = { ...baseConfig, amount: price };
  return handlePaidRequest(request, config);
}
```

---

## Async settlement

For lower latency, return data before on-chain settlement confirms. The facilitator still settles in the background.

```typescript
// Cloudflare Workers — use ctx.waitUntil for background settle
const outcome = await processPayment(
  config,
  request,
  { asyncSettle: true },
  ctx, // ExecutionContext
);

// Node.js — async settle runs as a floating promise (acceptable here because
// the facilitator is responsible for settlement, and failure doesn't affect
// the already-verified payment)
const outcome = await processPayment(
  config,
  request,
  { asyncSettle: true },
);
```
