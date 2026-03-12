# x402 Protocol Integration

## Overview

[x402](https://www.x402.org/) is an HTTP-native payment protocol that embeds stablecoin payments directly into HTTP request-response flows. It revives the HTTP 402 "Payment Required" status code to enable machine-native payments — no checkout pages, no card numbers, no human in the loop.

Radius is a strong fit for x402 because fees are low (~0.0001 USD per transaction), finality is sub-second (~500ms), and costs are predictable.

> **Protocol version:** This document targets **x402 v2**. v2 introduced CAIP-2 network identifiers, renamed HTTP headers, and standardized EIP-3009 as the required EVM token interface. See the [x402 v1→v2 migration guide](https://docs.x402.org/guides/migration-v1-to-v2.md) for the full diff.

## How x402 works

1. **Agent sends request** to your API or content endpoint.
2. **Your server returns HTTP 402** with payment terms (price, accepted tokens, facilitator URL) in the `PAYMENT-REQUIRED` header.
3. **Agent signs a payment** and resubmits the request with a `PAYMENT-SIGNATURE` header.
4. **Facilitator verifies payment** and settles it on Radius.
5. **Your server delivers the resource.**

```
Agent                        Your Server                  Facilitator          Radius
  |                              |                            |                  |
  |--- GET /api/data ---------->|                            |                  |
  |<-- 402 + PAYMENT-REQUIRED --|                            |                  |
  |                              |                            |                  |
  |--- GET /api/data ---------->|                            |                  |
  |    + PAYMENT-SIGNATURE      |--- verify + settle ------->|                  |
  |                              |                            |--- settle tx --->|
  |                              |                            |<-- receipt ------|
  |                              |<-- { ok, payer, txHash } --|                  |
  |<-- 200 OK + data -----------|                            |                  |
```

## Why Radius as the settlement layer

| Property | Base (x402 default) | Radius |
|----------|-------------------|--------|
| Max TPS | ~3,500 | 2.8M+ tested, linearly scalable |
| Cost per transaction | ~0.001–0.01 USD | ~0.00001 USD |
| Finality | ~2s | ~500ms |
| Gas fees | Variable (ETH for gas) | Fixed, near-zero, paid in stablecoins |
| Native token required | Yes (ETH) | No |

At current x402 volumes, Base works fine. As agent payment volume scales, the settlement layer becomes the bottleneck. Radius is designed for the rows where other infrastructure runs out of capacity.

## Request lifecycle

### Server returns 402

When a request hits a protected endpoint without payment proof:

```typescript
// Response headers
HTTP/1.1 402 Payment Required
PAYMENT-REQUIRED: <base64-encoded JSON>

// Response body
{
  "error": "Payment required",
  "x402Version": 2,
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:723",
      "maxAmountRequired": "100000",
      "resource": "https://api.example.com/premium/report",
      "description": "Access to /premium/report",
      "mimeType": "application/json",
      "payTo": "0xMERCHANT_ADDRESS",
      "asset": "0xTOKEN_ADDRESS",
      "maxTimeoutSeconds": 300
    }
  ]
}
```

### Client retries with payment

```
GET /premium/report
PAYMENT-SIGNATURE: <base64-encoded JSON with signed permit>
```

### Server confirms

```
HTTP/1.1 200 OK
X-Payment-Verified: true
X-Payment-Payer: 0x...
X-Payment-Transaction: 0x...
PAYMENT-RESPONSE: <base64-encoded settlement receipt>
```

`X-Payment-Verified`, `X-Payment-Payer`, and `X-Payment-Transaction` are application-level headers you set. `PAYMENT-RESPONSE` is the protocol-level header carrying the facilitator's encoded settlement receipt (the v2 replacement for `X-PAYMENT-RESPONSE`).

## Payment payload structure

```json
{
  "x402Version": 2,
  "scheme": "exact",
  "network": "eip155:723",
  "payload": {
    "kind": "permit-eip2612",
    "owner": "0x...",
    "spender": "0x...",
    "value": "1000000",
    "nonce": "0",
    "deadline": "1741500000",
    "v": 28,
    "r": "0x...",
    "s": "0x..."
  }
}
```

## Minimal endpoint pattern

Use this pattern in a gateway, API server, or edge worker:

```typescript
import { type Request, type Response } from 'express';

const PAYMENT_AMOUNT = '100000'; // 0.10 SBC (6 decimals)
const MERCHANT_ADDRESS = '0xYourMerchantAddress';
const TOKEN_ADDRESS = '0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb'; // SBC on mainnet
const RADIUS_MAINNET = 'eip155:723'; // CAIP-2 identifier for Radius mainnet

function handleRequest(req: Request, res: Response) {
  // Non-protected paths pass through
  if (!isProtectedPath(req.path)) {
    return serveResource(req, res);
  }

  // v2: header is PAYMENT-SIGNATURE (was X-Payment in v1)
  const xPayment = req.headers['payment-signature'] as string | undefined;

  // No payment header — return 402 with requirements
  if (!xPayment) {
    const requirement = {
      scheme: 'exact',
      network: RADIUS_MAINNET,
      maxAmountRequired: PAYMENT_AMOUNT,
      resource: req.url,
      description: 'Access to protected resource',
      payTo: MERCHANT_ADDRESS,
      asset: TOKEN_ADDRESS,
    };

    return res.status(402).json({
      error: 'Payment required',
      x402Version: 2,
      accepts: [requirement],
    });
  }

  // Payment header present — verify and settle
  const result = await facilitator.verifyAndSettle(xPayment);

  if (!result.ok) {
    return res.status(402).json({ error: result.error });
  }

  // Payment verified — serve the resource
  res.set('X-Payment-Verified', 'true');
  res.set('X-Payment-Payer', result.payer);
  res.set('X-Payment-Transaction', result.txHash);
  return serveResource(req, res);
}
```

## Token compatibility on Radius

The token you settle with determines which x402 strategies are available.

### v2 EVM token requirement

x402 v2 standardizes on **EIP-3009** (`transferWithAuthorization`) as the required interface for all EVM tokens. Tokens without EIP-3009 support require a custom facilitator path and lose several protocol guarantees (one-step atomicity, random nonces, explicit validity windows).

### EIP support overview

| Standard | USDC (FiatTokenV2_2) | SBC (Radius native) | Impact |
|----------|:---:|:---:|---|
| EIP-20 | ✅ | ✅ | Standard token transfers work |
| EIP-712 | ✅ | ✅ | Typed-data signatures work |
| EIP-2612 (`permit`) | ✅ | ✅ | Signature-based approvals work |
| EIP-3009 (`transferWithAuthorization`) | ✅ | ❌ | **Required for v2 EVM settlement.** SBC must use a custom two-step facilitator path |
| EIP-1271 (contract-wallet signatures) | ✅ | ❌ | Smart-account compatibility reduced |

### Why EIP-3009 matters more in v2

EIP-3009 enables `transferWithAuthorization` — a single atomic settlement transaction with no long-lived allowance footprint, concurrent authorization via random nonces, and explicit validity windows. In v2, this is the **standard expected path** for all EVM tokens. Any facilitator built to the v2 spec will default to this path.

Without EIP-3009, a facilitator must use EIP-2612 in two steps:

1. Call `permit()` to grant allowance.
2. Call `transferFrom()` to move funds.

This two-step path increases gas, adds latency, and introduces a non-atomic window. Because SBC does not implement EIP-3009, Radius x402 integrations using SBC require a custom facilitator that explicitly handles this path.

### Practical strategy for SBC on Radius

Use a custom facilitator path based on EIP-2612 `permit` + `transferFrom`:

- Enforce nonce, amount, and expiry validation.
- Enforce idempotency keys and replay protection.
- Monitor settlement outcomes for partial or failed two-step execution paths.
- Consider USDC (if bridged to Radius) for flows where EIP-3009 atomicity is required.

## Facilitator models

### Hosted facilitator

Use a hosted facilitator when:

- You need the fastest route to production.
- You want lower operational overhead.
- You want to validate demand before running settlement infrastructure.

**Radius x402 facilitator** (deploying to testnet):

- URL: `facilitator.testnet.radiustech.xyz`
- TypeScript-based, compatible with existing x402 client libraries and middleware.
- Supports per-request payments and HLS streaming payments.
- Free to use — facilitator absorbs gas fees.
- Repository: [github.com/radiustechsystems/x402-facilitator](https://github.com/radiustechsystems/x402-facilitator)

**Stablecoin.xyz** provides x402-compatible facilitator tooling for Radius:

- [Stablecoin.xyz x402 overview](https://docs.stablecoin.xyz/x402/overview)
- [Stablecoin.xyz x402 SDK](https://docs.stablecoin.xyz/x402/sdk)
- [Stablecoin.xyz x402 facilitator](https://docs.stablecoin.xyz/x402/facilitator)

### Custom facilitator

Build your own facilitator when:

- You need custom policy, risk, or compliance checks.
- You need custom settlement routing or treasury controls.
- You need full ownership of keys, infrastructure, and observability.

## Facilitator settlement pseudocode

The payment string arrives in the `PAYMENT-SIGNATURE` header. The function below handles both settlement strategies and reflects v2 field semantics (CAIP-2 network, `x402Version: 2`).

```typescript
async function verifyAndSettlePayment(
  xPayment: string,         // value of the PAYMENT-SIGNATURE header
  config: FacilitatorConfig
): Promise<SettlementResult> {
  const payment = decodeXPayment(xPayment);

  // Validate protocol version
  if (payment.x402Version !== 2) return { ok: false, error: 'Unsupported x402 version' };

  // Validate payment fields
  if (payment.scheme !== 'exact') return { ok: false, error: 'Unsupported scheme' };
  // Network uses CAIP-2 format: "eip155:723" (mainnet) or "eip155:72344" (testnet)
  if (payment.network !== config.network) return { ok: false, error: 'Wrong network' };
  if (payment.asset !== config.asset) return { ok: false, error: 'Wrong asset' };
  if (payment.payTo !== config.paymentAddress) return { ok: false, error: 'Wrong payTo' };

  if (payment.payload.kind === 'permit-eip2612') {
    // SBC path: two-step settlement via EIP-2612 permit + transferFrom
    // Note: EIP-3009 (single-step) is unavailable for SBC — see Token Compatibility section
    if (payment.payload.spender !== config.settlementSpender)
      return { ok: false, error: 'Wrong spender' };
    if (Date.now() / 1000 >= Number(payment.payload.deadline))
      return { ok: false, error: 'Permit expired' };
    if (BigInt(payment.payload.value) < config.requiredAmount)
      return { ok: false, error: 'Insufficient amount' };

    // Recover signer and validate
    const signer = recoverPermitSigner(payment.payload, config.domain);
    if (signer !== payment.payload.owner)
      return { ok: false, error: 'Invalid signature' };

    // Two-step settlement: permit then transferFrom
    await submitPermitTransaction(payment.payload);
    await assertAllowanceAtLeast(config.requiredAmount);
    const txHash = await submitTransferFrom(
      payment.payload.owner,
      config.paymentAddress,
      config.requiredAmount
    );

    return { ok: true, payer: payment.payload.owner, txHash };
  }

  if (payment.payload.kind === 'eip3009-transfer-with-authorization') {
    // Standard v2 EVM path: single-step settlement via EIP-3009
    // Available for USDC (and any EIP-3009 token) — NOT available for SBC
    if (BigInt(payment.payload.value) < config.requiredAmount)
      return { ok: false, error: 'Insufficient amount' };

    const now = Math.floor(Date.now() / 1000);
    if (now < Number(payment.payload.validAfter) || now > Number(payment.payload.validBefore))
      return { ok: false, error: 'Outside validity window' };

    const txHash = await submitTransferWithAuthorization(payment.payload);
    return { ok: true, payer: payment.payload.from, txHash };
  }

  return { ok: false, error: 'Unsupported settlement strategy' };
}
```

## Validation checklist

Before settlement, validate:

- [ ] `x402Version` is `2`
- [ ] `scheme` matches expected value (for example, `exact`)
- [ ] `network` is the correct CAIP-2 identifier for Radius (`eip155:723` mainnet, `eip155:72344` testnet)
- [ ] `asset` matches the accepted token contract
- [ ] `payTo` matches your payment address
- [ ] Signed amount ≥ required amount
- [ ] Signature is valid and signer identity matches payload
- [ ] Nonce and validity window checks pass
- [ ] Payer balance is sufficient
- [ ] Settlement wallet has enough RUSD for gas

After settlement:

- [ ] Wait for transaction receipt (sub-second on Radius)
- [ ] Return deterministic success metadata
- [ ] Store idempotency key and transaction hash for replay prevention

## What you can build

### Per-request API monetization

Add x402 middleware to any HTTP endpoint. Agents pay per API call, per data retrieval, or per query. Your existing service logic doesn't change.

Use cases: data feeds, inference endpoints, translation services, geocoding, search APIs, premium content access.

### Streaming payments

For continuous consumption (video streaming, real-time data feeds, GPU compute, LLM token generation), x402 on Radius supports per-segment or per-second payment flows. The Radius facilitator supports HLS streaming, where each segment triggers an automatic micropayment.

### Pay-per-crawl content gating

Serve content to AI crawlers for a per-page fee instead of blocking them entirely. Return a 402 response to agent traffic with your price — agents that pay get access, agents that don't get blocked. Monetize crawler traffic without losing distribution.

## Radius-specific configuration notes

- Configure clients and settlement services with Radius network settings (see [network-config.md](network-config.md)).
- Use the CAIP-2 network identifier for Radius: `eip155:723` (mainnet), `eip155:72344` (testnet).
- Use Radius-compatible fee handling in transaction paths (see [evm-differences.md](evm-differences.md)).
- Keep settlement wallets funded with RUSD for gas.
- Use short validity windows to reduce replay risk.
- Add structured logs for verification failures and settlement outcomes.

## Header reference (v1 → v2)

| Purpose | v1 Header | v2 Header |
|---------|-----------|-----------|
| 402 payment terms (server → client) | `X-Accept-Payment` | `PAYMENT-REQUIRED` |
| Payment proof (client → server) | `X-Payment` | `PAYMENT-SIGNATURE` |
| Facilitator settlement response | `X-PAYMENT-RESPONSE` | `PAYMENT-RESPONSE` |

The application-level success headers (`X-Payment-Verified`, `X-Payment-Payer`, `X-Payment-Transaction`) are not protocol-defined — you set them yourself and can name them however you like.

## Package reference (v1 → v2)

| v1 Package | v2 Package |
|------------|------------|
| `x402` | `@x402/core` |
| `x402-express` | `@x402/express` |
| `x402-axios` | `@x402/axios` |
| `x402-fetch` | `@x402/fetch` |
| `x402-next` | `@x402/next` |
| `x402-hono` | `@x402/hono` |
| *(built-in)* | `@x402/evm` (EVM scheme support) |

## Migration from Base

If you're settling x402 payments on Base today, moving to Radius is a configuration change:

```typescript
// Base configuration (v2 CAIP-2 format)
const SETTLEMENT_RPC = 'https://mainnet.base.org';
const NETWORK = 'eip155:8453';

const SETTLEMENT_RPC = 'https://rpc.radiustech.xyz';
const NETWORK = 'eip155:723';
```

You keep the same smart contracts, same wallets, same stablecoin, same x402 protocol integration.

## Related resources

- [x402.org](https://www.x402.org/) — Protocol specification
- [x402 v1→v2 migration guide](https://docs.x402.org/guides/migration-v1-to-v2.md) — Full protocol diff
- [x402 network and token support](https://docs.x402.org/core-concepts/network-and-token-support.md) — CAIP-2 identifiers and EIP-3009 requirements
- [Radius x402 Facilitator (GitHub)](https://github.com/radiustechsystems/x402-facilitator) — Watch for deployment updates
- [Stablecoin.xyz x402 docs](https://docs.stablecoin.xyz/x402/overview) — Hosted facilitator tooling
- [Network config](network-config.md) — Radius endpoints and chain IDs
- [Fees and Turnstile](evm-differences.md) — Fee model for settlement transactions
- [Gotchas](gotchas.md) — Production issues affecting x402 flows (permits, nonces, decimals)
