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
  /** HTTP header carrying the payment (default: "PAYMENT-SIGNATURE") */
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

/** The x402 v2 payment-required object sent in the PAYMENT-REQUIRED header. */
export interface PaymentRequired {
  x402Version: 2;
  error: string;
  resource: {
    url: string;
    description?: string;
    mimeType?: string;
  };
  accepts: PaymentRequirement[];
  extensions?: Record<string, unknown>;
}

/** Settlement metadata sent in the PAYMENT-RESPONSE header. */
export interface SettlementResponse {
  success: boolean;
  transaction?: string;
  txHash?: string;
  transactionHash?: string;
  hash?: string;
  payer?: string;
  network: string;
  errorReason?: string;
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
  | { status: 'no-payment'; paymentRequired: PaymentRequired }
  | { status: 'invalid-header' }
  | { status: 'verify-failed'; detail: any }
  | { status: 'verify-unreachable'; detail: string }
  | { status: 'settle-failed'; detail: any }
  | { status: 'settle-unreachable'; detail: string }
  | { status: 'settled'; txHash: string | undefined; settlementResponse: SettlementResponse; verifyMs: number; settleMs: number; totalMs: number }
  | { status: 'settle-pending'; verifyMs: number; totalMs: number };
```

---

## Core functions

### buildPaymentRequired

Constructs the x402 v2 `PaymentRequired` object sent to clients in the `PAYMENT-REQUIRED` header.

```typescript
export function buildPaymentRequirement(config: X402Config): PaymentRequirement {
  return {
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
  };
}

export function buildEip2612GasSponsoringExtension() {
  return {
    info: {
      description: 'The facilitator accepts EIP-2612 gasless Permit to the canonical Permit2 contract.',
      version: '1',
    },
    schema: {
      $schema: 'https://json-schema.org/draft/2020-12/schema',
      type: 'object',
      properties: {
        from: { type: 'string', pattern: '^0x[a-fA-F0-9]{40}$' },
        asset: { type: 'string', pattern: '^0x[a-fA-F0-9]{40}$' },
        spender: { type: 'string', pattern: '^0x[a-fA-F0-9]{40}$' },
        amount: { type: 'string', pattern: '^[0-9]+$' },
        nonce: { type: 'string', pattern: '^[0-9]+$' },
        deadline: { type: 'string', pattern: '^[0-9]+$' },
        signature: { type: 'string', pattern: '^0x[a-fA-F0-9]+$' },
        version: { type: 'string', pattern: '^[0-9]+(\\.[0-9]+)*$' },
      },
      required: ['from', 'asset', 'spender', 'amount', 'nonce', 'deadline', 'signature', 'version'],
    },
  };
}

export function buildPaymentRequired(config: X402Config, request: Request): PaymentRequired {
  return {
    x402Version: 2,
    error: 'PAYMENT-SIGNATURE header is required',
    resource: {
      url: request.url,
      description: `Access to ${new URL(request.url).pathname}`,
      mimeType: 'application/json',
    },
    accepts: [buildPaymentRequirement(config)],
    extensions: {
      eip2612GasSponsoring: buildEip2612GasSponsoringExtension(),
    },
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
  const headerName = config.paymentHeader ?? 'PAYMENT-SIGNATURE';
  const paymentHeader = request.headers.get(headerName);

  // No payment header -> return requirements for the PAYMENT-REQUIRED header.
  if (!paymentHeader) {
    return { status: 'no-payment', paymentRequired: buildPaymentRequired(config, request) };
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
    paymentRequirements: buildPaymentRequirement(config),
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

    const verifyData: any = await readFacilitatorJson(verifyRes);
    if (!verifyRes.ok || !verifyData.isValid) {
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
      .then(readFacilitatorJson)
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

  const settleData: any = await readFacilitatorJson(settleRes);
  if (!settleRes.ok || !settleData.success) {
    return { status: 'settle-failed', detail: settleData };
  }

  // Facilitator may return tx hash under different field names
  const txHash =
    settleData.transaction ??
    settleData.txHash ??
    settleData.transactionHash ??
    settleData.hash;

  return { status: 'settled', txHash, settlementResponse: settleData, verifyMs, settleMs, totalMs: Date.now() - t0 };
}
```

---

## Helpers

```typescript
/** CORS headers that include the payment header. */
export function corsHeaders(config?: Partial<X402Config>): Record<string, string> {
  const header = config?.paymentHeader ?? 'PAYMENT-SIGNATURE';
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': `Content-Type, ${header}`,
    'Access-Control-Expose-Headers': 'PAYMENT-REQUIRED, PAYMENT-RESPONSE',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  };
}

/** Base64-encode JSON in browser, Workers, or Node.js runtimes. */
export function encodeBase64Json(data: unknown): string {
  const json = JSON.stringify(data);
  if (typeof btoa === 'function') return btoa(json);
  return Buffer.from(json, 'utf8').toString('base64');
}

/** JSON response with CORS headers. */
export function jsonResponse(
  data: unknown,
  status = 200,
  config?: Partial<X402Config>,
  extraHeaders: Record<string, string> = {},
): Response {
  return Response.json(data, {
    status,
    headers: { ...corsHeaders(config), 'Content-Type': 'application/json', ...extraHeaders },
  });
}

/** Parse JSON if present; preserve status/body details for facilitator errors. */
async function readFacilitatorJson(response: Response): Promise<any> {
  const text = await response.text();
  if (!text) return { status: response.status, ok: response.ok };
  try {
    return JSON.parse(text);
  } catch {
    return { status: response.status, ok: response.ok, body: text };
  }
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
      return jsonResponse({}, 402, config, {
        'PAYMENT-REQUIRED': encodeBase64Json(outcome.paymentRequired),
      });

    case 'invalid-header':
      return jsonResponse({ error: 'Invalid PAYMENT-SIGNATURE header' }, 400, config);

    case 'verify-failed':
      return jsonResponse(
        { error: 'Payment verification failed', detail: outcome.detail },
        402,
        config,
        { 'PAYMENT-REQUIRED': encodeBase64Json(buildPaymentRequired(config, request)) },
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
        402,
        config,
        { 'PAYMENT-RESPONSE': encodeBase64Json(outcome.detail) },
      );

    case 'settle-pending':
      return jsonResponse({ message: 'Payment accepted', path: url.pathname }, 200, config);

    case 'settled':
      // Payment accepted — return the paid content
      // Replace with your application logic:
      return jsonResponse({ message: 'Payment accepted', path: url.pathname }, 200, config, {
        'PAYMENT-RESPONSE': encodeBase64Json(outcome.settlementResponse),
      });
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
      facilitatorUrl: 'https://facilitator.radiustech.xyz',
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
  facilitatorUrl: 'https://facilitator.radiustech.xyz',
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
  res.set(corsHeaders(config));

  if (outcome.status === 'settled' || outcome.status === 'settle-pending') {
    if (outcome.status === 'settled') {
      res.set('PAYMENT-RESPONSE', encodeBase64Json(outcome.settlementResponse));
    }
    next(); // Payment accepted — proceed to route handler
    return;
  }

  // Map outcome to HTTP response
  if (outcome.status === 'no-payment') {
    res
      .status(402)
      .set('PAYMENT-REQUIRED', encodeBase64Json(outcome.paymentRequired))
      .json({});
  } else if (outcome.status === 'invalid-header') {
    res.status(400).json({ error: 'Invalid PAYMENT-SIGNATURE header' });
  } else if (outcome.status === 'verify-failed' || outcome.status === 'settle-failed') {
    const responseHeader = outcome.status === 'settle-failed'
      ? { 'PAYMENT-RESPONSE': encodeBase64Json(outcome.detail) }
      : { 'PAYMENT-REQUIRED': encodeBase64Json(buildPaymentRequired(config, request)) };
    res
      .status(402)
      .set(responseHeader)
      .json({ error: 'Payment failed', detail: outcome.detail });
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
  facilitatorUrl: 'https://facilitator.radiustech.xyz',
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

  for (const [key, value] of Object.entries(corsHeaders(config))) {
    res.setHeader(key, value);
  }
  res.setHeader('Content-Type', 'application/json');
  if (outcome.status === 'no-payment') {
    res.setHeader('PAYMENT-REQUIRED', encodeBase64Json(outcome.paymentRequired));
    res.writeHead(402);
    res.end(JSON.stringify({}));
  } else if (outcome.status === 'settled') {
    res.setHeader('PAYMENT-RESPONSE', encodeBase64Json(outcome.settlementResponse));
    res.writeHead(200);
    res.end(JSON.stringify({ data: 'your protected content' }));
  } else if (outcome.status === 'settle-pending') {
    res.writeHead(200);
    res.end(JSON.stringify({ data: 'your protected content' }));
  } else if (outcome.status === 'verify-failed' || outcome.status === 'settle-failed') {
    if (outcome.status === 'settle-failed') {
      res.setHeader('PAYMENT-RESPONSE', encodeBase64Json(outcome.detail));
    } else {
      res.setHeader('PAYMENT-REQUIRED', encodeBase64Json(buildPaymentRequired(config, request)));
    }
    res.writeHead(402);
    res.end(JSON.stringify({ error: 'Payment failed', detail: outcome.detail }));
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
