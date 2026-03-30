# TypeScript Reference (viem)

## Overview

All Radius TypeScript integration uses **plain viem** — no wrapper SDK. You define the Radius chain with `defineChain`, create clients with `createPublicClient` and `createWalletClient`, and interact with contracts using viem's standard APIs.

## Installation

```bash
pnpm add viem
```

Requirements:
- Node.js >= 18
- TypeScript 5+ (recommended)

## Chain definition

Define the Radius chain with `fees.estimateFeesPerGas()` so viem always uses the correct fixed gas price. The fee override queries `eth_gasPrice` from the RPC and sets both EIP-1559 fee fields to the same value:

```typescript
import { defineChain } from 'viem';
import type { Chain, Client } from 'viem';

const radiusFees = {
  async estimateFeesPerGas(args: { client: Client }) {
    const gasPrice = await args.client.request({ method: 'eth_gasPrice' });
    const price = BigInt(gasPrice);
    return { maxFeePerGas: price, maxPriorityFeePerGas: price };
  },
} satisfies Chain['fees'];

export const radiusTestnet = defineChain({
  id: 72344,
  name: 'Radius Testnet',
  nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
  rpcUrls: {
    default: { http: ['https://rpc.testnet.radiustech.xyz'] },
  },
  blockExplorers: {
    default: { name: 'Radius Testnet Explorer', url: 'https://testnet.radiustech.xyz' },
  },
  fees: radiusFees,
});

export const radiusMainnet = defineChain({
  id: 723487,
  name: 'Radius Network',
  nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
  rpcUrls: {
    default: { http: ['https://rpc.radiustech.xyz'] },
  },
  blockExplorers: {
    default: { name: 'Radius Explorer', url: 'https://network.radiustech.xyz' },
  },
  fees: radiusFees,
});
```

> **Important:** Always include `fees.estimateFeesPerGas()`. Without it, viem may derive invalid fee values and transactions will fail silently.

## Quick start

```typescript
import { createPublicClient, createWalletClient, http, parseEther } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';

// Use the radiusTestnet definition from above

// Public client for read operations
const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

// Account from private key
const account = privateKeyToAccount(
  process.env.RADIUS_PRIVATE_KEY as `0x${string}`
);

// Wallet client for write operations
const walletClient = createWalletClient({
  account,
  chain: radiusTestnet,
  transport: http(),
});

// Check balance
const balance = await publicClient.getBalance({ address: account.address });
console.log('Balance:', balance);

// Send a transaction
const hash = await walletClient.sendTransaction({
  to: '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  value: parseEther('0.5'),
});

// Wait for confirmation (~200-500ms on Radius, transaction is FINAL)
const receipt = await publicClient.waitForTransactionReceipt({ hash });
console.log('Status:', receipt.status);
```

## Core concepts

### Public client

Handles read operations that don't require signing:

```typescript
import { createPublicClient, http } from 'viem';

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const balance = await publicClient.getBalance({ address: '0x...' });
const blockNumber = await publicClient.getBlockNumber();
const chainId = await publicClient.getChainId();
```

### Wallet client

Handles write operations that require signing:

```typescript
import { createWalletClient, http } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';

const account = privateKeyToAccount('0x...');

const walletClient = createWalletClient({
  account,
  chain: radiusTestnet,
  transport: http(),
});
```

## Read operations

```typescript
// Get balance
// NOTE: On Radius, this returns native balance + convertible USD balance
const balance = await publicClient.getBalance({
  address: '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1',
});

// Get block number (NOTE: returns timestamp in ms on Radius, not sequential height)
const blockNumber = await publicClient.getBlockNumber();

// Get transaction count (nonce)
const nonce = await publicClient.getTransactionCount({
  address: '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1',
});

// Get transaction receipt
const receipt = await publicClient.getTransactionReceipt({
  hash: '0x...',
});

// Estimate gas
const gas = await publicClient.estimateGas({
  to: '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1',
  value: parseEther('1'),
});

// Get contract code
const code = await publicClient.getCode({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
});
```

## Write operations

```typescript
import { parseEther } from 'viem';

// Send native tokens (RUSD on Radius)
const hash = await walletClient.sendTransaction({
  to: '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  value: parseEther('0.5'),
});

// Wait for receipt (~200-500ms on Radius, transaction is FINAL)
const receipt = await publicClient.waitForTransactionReceipt({ hash });

if (receipt.status === 'success') {
  console.log('Transaction confirmed in block:', receipt.blockNumber);
} else {
  console.error('Transaction reverted');
}
```

### Send and wait pattern

```typescript
async function sendAndWait(
  walletClient: WalletClient,
  publicClient: PublicClient,
  to: `0x${string}`,
  value: bigint
) {
  const hash = await walletClient.sendTransaction({ to, value });
  return publicClient.waitForTransactionReceipt({ hash });
}

const receipt = await sendAndWait(
  walletClient,
  publicClient,
  '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  parseEther('0.5')
);
```

## Contract interactions

Use viem's `getContract` for type-safe contract interactions:

```typescript
import { getContract, parseAbi } from 'viem';

const abi = parseAbi([
  'function balanceOf(address) view returns (uint256)',
  'function transfer(address to, uint256 amount) returns (bool)',
  'event Transfer(address indexed from, address indexed to, uint256 value)',
]);

const contract = getContract({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  abi,
  client: { public: publicClient, wallet: walletClient },
});

// Read from contract
const balance = await contract.read.balanceOf([account.address]);
console.log('Token balance:', balance);

// Write to contract
const hash = await contract.write.transfer([
  '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  1000000000000000000n,
]);

const receipt = await publicClient.waitForTransactionReceipt({ hash });
```

### Deploy a contract

```typescript
const bytecode = '0x608060...';
const abi = [...];

const hash = await walletClient.deployContract({
  abi,
  bytecode,
  args: ['Constructor Arg 1', 42n],
});

const receipt = await publicClient.waitForTransactionReceipt({ hash });

if (receipt.status === 'success' && receipt.contractAddress) {
  console.log('Deployed at:', receipt.contractAddress);
}
```

## ERC-20 token operations

### Check token balance

```typescript
import { getContract, erc20Abi } from 'viem';

const token = getContract({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  abi: erc20Abi,
  client: publicClient,
});

const balance = await token.read.balanceOf([account.address]);
const decimals = await token.read.decimals();
const symbol = await token.read.symbol();

console.log(`Balance: ${balance} ${symbol} (${decimals} decimals)`);
```

### Transfer tokens

```typescript
import { getContract, erc20Abi } from 'viem';

const token = getContract({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  abi: erc20Abi,
  client: { public: publicClient, wallet: walletClient },
});

// Transfer 1 SBC token (6 decimals)
const hash = await token.write.transfer([
  '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  1000000n, // 1.0 SBC = 1_000_000 base units (6 decimals)
]);

const receipt = await publicClient.waitForTransactionReceipt({ hash });

if (receipt.status === 'success') {
  console.log('Transfer complete:', receipt.transactionHash);
}
```

> **Critical:** SBC uses **6 decimals** on both testnet and mainnet. Always use `parseUnits(amount, 6)` for SBC and `parseEther(amount)` for RUSD (native token). See [gotchas.md](gotchas.md).

### Approve and transferFrom

```typescript
// Approve spender
const approveHash = await token.write.approve([
  '0x70997970C51812dc3A010C7d01b50e0d17dc79C8', // spender
  1000000000000000000n, // amount
]);

await publicClient.waitForTransactionReceipt({ hash: approveHash });

// Check allowance
const allowance = await token.read.allowance([
  account.address,
  '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
]);
```

## Sending multiple transactions

For sending multiple transactions, use sequential sends or `Promise.all`:

```typescript
import { parseEther } from 'viem';

const recipients = [
  '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC',
  '0x90F79bf6EB2c4f870365E785982E1f101E93b906',
] as const;

// Send sequentially (safer — avoids nonce collisions)
const hashes: `0x${string}`[] = [];
for (const to of recipients) {
  const hash = await walletClient.sendTransaction({
    to,
    value: parseEther('0.1'),
  });
  hashes.push(hash);
}

// Wait for all receipts
const receipts = await Promise.all(
  hashes.map((hash) => publicClient.waitForTransactionReceipt({ hash }))
);
```

> **Gotcha:** If you send concurrent transactions from the same wallet, you will hit nonce collisions. Radius enforces strict sequential nonces. Always send sequentially from a single wallet, or use a nonce-aware queue. See [gotchas.md](gotchas.md#7-nonce-collisions-under-concurrent-load).

For batching **reads**, use Multicall3 (deployed at `0xcA11bde05977b3631167028862bE2a173976CA11`):

```typescript
const results = await publicClient.multicall({
  contracts: [
    { address: tokenAddress, abi: erc20Abi, functionName: 'balanceOf', args: [addr1] },
    { address: tokenAddress, abi: erc20Abi, functionName: 'balanceOf', args: [addr2] },
    { address: tokenAddress, abi: erc20Abi, functionName: 'totalSupply' },
  ],
});
```

## Account management

### Create account from private key

```typescript
import { privateKeyToAccount } from 'viem/accounts';

const account = privateKeyToAccount(
  '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'
);

console.log('Address:', account.address);
```

### Generate a random wallet

```typescript
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts';

const privateKey = generatePrivateKey();
const account = privateKeyToAccount(privateKey);

console.log('New address:', account.address);
console.log('Private key:', privateKey);
```

### Use environment variables (always do this)

```typescript
import { privateKeyToAccount } from 'viem/accounts';

const privateKey = process.env.RADIUS_PRIVATE_KEY as `0x${string}`;
if (!privateKey) {
  throw new Error('RADIUS_PRIVATE_KEY environment variable not set');
}

const account = privateKeyToAccount(privateKey);
```

Run with:

```bash
node --env-file=.env --import=tsx your-script.ts
```

### Test accounts

Anvil Account 0 is funded on Radius Testnet:

```
Address:     0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
Private Key: 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

Account 1:

```
Address:     0x70997970C51812dc3A010C7d01b50e0d17dc79C8
Private Key: 0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
```

These are well-known test keys. **Never use them in production.**

For other accounts, fund via the faucet (see Radius "dripping faucet" skill).

## Error handling

```typescript
import {
  ContractFunctionExecutionError,
  TransactionExecutionError,
  InsufficientFundsError,
} from 'viem';

try {
  const hash = await walletClient.sendTransaction({
    to: '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
    value: parseEther('1000'),
  });

  const receipt = await publicClient.waitForTransactionReceipt({ hash });
  console.log('Success:', receipt.transactionHash);
} catch (error) {
  if (error instanceof InsufficientFundsError) {
    console.error('Insufficient balance for transaction');
  } else if (error instanceof TransactionExecutionError) {
    console.error('Transaction failed:', error.shortMessage);
  } else if (error instanceof ContractFunctionExecutionError) {
    console.error('Contract call failed:', error.shortMessage);
  } else {
    throw error;
  }
}
```

### Common error types

| Error Type | Cause |
|-----------|-------|
| `InsufficientFundsError` | Balance too low for transaction + gas |
| `TransactionExecutionError` | Transaction failed during execution |
| `ContractFunctionExecutionError` | Contract method reverted |
| `UserRejectedRequestError` | User rejected wallet prompt |
| `ChainMismatchError` | Wrong chain selected in wallet |

## Custom transport options

```typescript
const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http('https://rpc.testnet.radiustech.xyz', {
    timeout: 30_000,
    retryCount: 3,
    retryDelay: 1000,
  }),
});
```

## TypeScript types

viem provides full TypeScript support with strict types:

```typescript
import type {
  Address,
  Hash,
  Hex,
  TransactionReceipt,
  PublicClient,
  WalletClient,
  LocalAccount,
  Chain,
} from 'viem';

// Type-safe address
const recipient: Address = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8';

// Type-safe transaction hash
const txHash: Hash = '0xabc123...';

// Function with typed parameters
async function transfer(
  client: WalletClient,
  to: Address,
  value: bigint
): Promise<Hash> {
  return client.sendTransaction({ to, value });
}
```

## EIP-7966: Synchronous transactions

Radius supports `eth_sendRawTransactionSync` (EIP-7966), which submits a transaction and waits for the receipt in a single RPC call — roughly 50% less latency than the standard `sendTransaction` + `waitForTransactionReceipt` polling pattern.

```typescript
import { serializeTransaction, signTransaction } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';

const account = privateKeyToAccount(process.env.RADIUS_PRIVATE_KEY as `0x${string}`);

// Sign the transaction
const signedTx = await account.signTransaction({
  to: '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  value: 1000000n,
  chainId: radiusTestnet.id,
  gasPrice: await publicClient.getGasPrice(),
  gas: 21000n,
  nonce: await publicClient.getTransactionCount({ address: account.address }),
});

// Submit synchronously — returns receipt directly (no polling)
const result = await publicClient.request({
  method: 'eth_sendRawTransactionSync' as any,
  params: [signedTx],
});
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `signedTx` | hex string | Yes | Signed raw transaction |
| `timeout` | number | No | Timeout in ms (default: 2000) |

### Error codes

| Code | Meaning | Action |
|------|---------|--------|
| 4 | Timeout — receipt not ready in time | Retry or fall back to `waitForTransactionReceipt` |
| 5 | Unknown / queued — tx accepted but not yet executed | Poll with `getTransactionReceipt` |
| 6 | Nonce gap — a prior nonce is missing | Fix nonce sequencing, then retry |

> **When to use:** Ideal for latency-sensitive server-side flows (API metering, settlement). For browser wallets, stick with `sendTransaction` + `waitForTransactionReceipt` since the wallet handles signing.

## Network reference

| Setting | Testnet | Mainnet |
|---------|---------|---------|
| **RPC Endpoint** | `https://rpc.testnet.radiustech.xyz` | `https://rpc.radiustech.xyz` |
| **Chain ID** | `72344` | `723487` |
| **Native Token** | RUSD (18 decimals) | RUSD (18 decimals) |
| **SBC Token** | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` (6 decimals) | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` (6 decimals) |
| **Block Explorer** | `https://testnet.radiustech.xyz` | `https://network.radiustech.xyz` |
| **Tx Cost API** | `https://testnet.radiustech.xyz/api/v1/network/transaction-cost` | `https://network.radiustech.xyz/api/v1/network/transaction-cost` |
