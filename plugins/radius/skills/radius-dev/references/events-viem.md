# Events Reference (viem)

## Overview

Radius supports standard EVM event watching and log queries using **plain viem** — no wrapper SDK needed. Use `publicClient.watchContractEvent()` for real-time subscriptions, `publicClient.getLogs()` for historical queries, and `publicClient.watchBlockNumber()` for block monitoring.

## Setup

Create a public client with the Radius chain definition (see [typescript-viem.md](typescript-viem.md) for the full `defineChain` pattern including `fees.estimateFeesPerGas()`):

```typescript
import { createPublicClient, http } from 'viem';
import { radiusTestnet } from './chain'; // See SKILL.md "Canonical chain definitions" to create this file

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});
```

## Watch block numbers

Subscribe to new blocks:

```typescript
const unwatch = publicClient.watchBlockNumber({
  onBlockNumber: (blockNumber) => {
    console.log('New block:', blockNumber);
    // NOTE: On Radius, block numbers are timestamps in milliseconds, not sequential heights
  },
  onError: (error) => {
    console.error('Block watch error:', error);
  },
});

// Stop watching when done
unwatch();
```

## Watch ERC-20 transfers

### Basic transfer watching

```typescript
import { erc20Abi } from 'viem';

const unwatch = publicClient.watchContractEvent({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb', // Token contract
  abi: erc20Abi,
  eventName: 'Transfer',
  onLogs: (logs) => {
    for (const log of logs) {
      console.log('Transfer:', {
        from: log.args.from,
        to: log.args.to,
        value: log.args.value,
        txHash: log.transactionHash,
      });
    }
  },
  onError: (error) => {
    console.error('Transfer watch error:', error);
  },
});

// Stop watching when done
unwatch();
```

### Filter by sender

```typescript
const unwatch = publicClient.watchContractEvent({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  abi: erc20Abi,
  eventName: 'Transfer',
  args: {
    from: '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266',
  },
  onLogs: (logs) => {
    console.log('Outgoing transfers:', logs.length);
  },
});
```

### Filter by recipient

```typescript
const unwatch = publicClient.watchContractEvent({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  abi: erc20Abi,
  eventName: 'Transfer',
  args: {
    to: '0x70997970C51812dc3A010C7d01b50e0d17dc79C8',
  },
  onLogs: (logs) => {
    console.log('Incoming transfers:', logs.length);
  },
});
```

### Watch transfers for a specific address (sent and received)

To watch both directions, set up two watchers:

```typescript
const ADDRESS = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266';
const TOKEN = '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb';

const unwatchOutgoing = publicClient.watchContractEvent({
  address: TOKEN,
  abi: erc20Abi,
  eventName: 'Transfer',
  args: { from: ADDRESS },
  onLogs: (logs) => {
    for (const log of logs) {
      console.log('Sent:', log.args.value, 'to', log.args.to);
    }
  },
});

const unwatchIncoming = publicClient.watchContractEvent({
  address: TOKEN,
  abi: erc20Abi,
  eventName: 'Transfer',
  args: { to: ADDRESS },
  onLogs: (logs) => {
    for (const log of logs) {
      console.log('Received:', log.args.value, 'from', log.args.from);
    }
  },
});

// Cleanup both
function stopWatching() {
  unwatchOutgoing();
  unwatchIncoming();
}
```

## Watch approvals

```typescript
const unwatch = publicClient.watchContractEvent({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  abi: erc20Abi,
  eventName: 'Approval',
  onLogs: (logs) => {
    for (const log of logs) {
      console.log('Approval granted:', {
        owner: log.args.owner,
        spender: log.args.spender,
        value: log.args.value,
      });
    }
  },
});
```

## Watch custom events

For any custom event, use `parseAbiItem` to define the event signature:

```typescript
import { parseAbiItem } from 'viem';

const unwatch = publicClient.watchContractEvent({
  address: '0x...your-contract...',
  abi: [
    parseAbiItem(
      'event PaymentReceived(address indexed payer, uint256 amount, bytes32 orderId)'
    ),
  ],
  eventName: 'PaymentReceived',
  onLogs: (logs) => {
    for (const log of logs) {
      console.log('Payment received:', log.args);
    }
  },
});
```

## Watch all events from a contract

Use `watchEvent` for unfiltered logs from a contract address:

```typescript
const unwatch = publicClient.watchEvent({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  onLogs: (logs) => {
    for (const log of logs) {
      console.log('Event:', log);
    }
  },
});
```

## Query historical logs

### Basic log query

```typescript
import { erc20Abi, parseAbiItem } from 'viem';

const transferEvent = parseAbiItem(
  'event Transfer(address indexed from, address indexed to, uint256 value)'
);

const logs = await publicClient.getLogs({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  event: transferEvent,
  fromBlock: 1000000n,
  toBlock: 1010000n,
});

console.log(`Found ${logs.length} transfer events`);

for (const log of logs) {
  console.log({
    from: log.args.from,
    to: log.args.to,
    value: log.args.value,
    block: log.blockNumber,
    txHash: log.transactionHash,
  });
}
```

### Query with filters

```typescript
const logs = await publicClient.getLogs({
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  event: transferEvent,
  args: {
    from: '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266',
  },
  fromBlock: 1000000n,
  toBlock: 1010000n,
});
```

### Paginated log queries for large ranges

Radius **requires** an `address` filter on all `eth_getLogs` calls (error `-33014` without it). The block range is capped at 1,000,000 units (~16 min 40 sec due to ms-granularity block numbers; error `-33002` if exceeded). Paginate large queries by chunking:

```typescript
async function getLogsPaginated(
  publicClient: PublicClient,
  params: {
    address: `0x${string}`;
    event: any;
    fromBlock: bigint;
    toBlock: bigint;
    chunkSize?: number;
    onProgress?: (info: { currentBlock: bigint; totalBlocks: bigint; logsFetched: number }) => void;
  }
) {
  const { address, event, fromBlock, toBlock, chunkSize = 1000, onProgress } = params;
  const allLogs: any[] = [];
  const totalBlocks = toBlock - fromBlock;

  let currentFrom = fromBlock;
  while (currentFrom <= toBlock) {
    const currentTo = currentFrom + BigInt(chunkSize) - 1n > toBlock
      ? toBlock
      : currentFrom + BigInt(chunkSize) - 1n;

    try {
      const logs = await publicClient.getLogs({
        address,
        event,
        fromBlock: currentFrom,
        toBlock: currentTo,
      });
      allLogs.push(...logs);
    } catch (err) {
      // If "block range too wide", reduce chunk size and retry
      const msg = (err as Error).message || '';
      if (msg.includes('block range') && chunkSize > 10) {
        const smallerChunk = Math.floor(chunkSize / 2);
        const subLogs = await getLogsPaginated(publicClient, {
          address,
          event,
          fromBlock: currentFrom,
          toBlock: currentTo,
          chunkSize: smallerChunk,
          onProgress,
        });
        allLogs.push(...subLogs);
        currentFrom = currentTo + 1n;
        continue;
      }
      throw err;
    }

    onProgress?.({
      currentBlock: currentTo,
      totalBlocks,
      logsFetched: allLogs.length,
    });

    currentFrom = currentTo + 1n;
  }

  return allLogs;
}

// Usage
const logs = await getLogsPaginated(publicClient, {
  address: '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb',
  event: transferEvent,
  fromBlock: 0n,
  toBlock: 1000000n,
  chunkSize: 1000,
  onProgress: ({ currentBlock, totalBlocks, logsFetched }) => {
    const pct = totalBlocks > 0n
      ? (Number(currentBlock) / Number(totalBlocks) * 100).toFixed(1)
      : '100';
    console.log(`Progress: ${pct}% (${logsFetched} logs)`);
  },
});
```

## Decode event logs

Parse raw logs into typed event data using viem's `decodeEventLog`:

```typescript
import { decodeEventLog, erc20Abi } from 'viem';

// Decode a single log
const decoded = decodeEventLog({
  abi: erc20Abi,
  data: rawLog.data,
  topics: rawLog.topics,
});

console.log('Event:', decoded.eventName);
console.log('Args:', decoded.args);
```

For filtering decoded logs by event name:

```typescript
import { parseEventLogs } from 'viem';

const parsed = parseEventLogs({
  abi: erc20Abi,
  logs: rawLogs,
  eventName: 'Transfer',
});

for (const transfer of parsed) {
  console.log('Transfer:', transfer.args);
}
```

## WebSocket transport

Use WebSocket for lower-latency real-time event subscriptions:

```typescript
import { createPublicClient, webSocket } from 'viem';

const wsClient = createPublicClient({
  chain: radiusTestnet,
  transport: webSocket('wss://rpc.testnet.radiustech.xyz'),
});

// Real-time log subscription (the ONLY supported WebSocket subscription type)
const unwatch = wsClient.watchContractEvent({
  address: contractAddress,
  abi: contractAbi,
  eventName: 'Transfer',
  onLogs: (logs) => {
    // process logs
  },
});
```

> **Warning:** WebSocket RPC on Radius requires an API key with elevated privileges. **Only `logs` subscriptions are supported.** `newHeads`, `newPendingTransactions`, and `syncing` subscriptions return error `-32602`. `watchBlockNumber` via WebSocket will NOT work — use HTTP polling (`eth_blockNumber` on a 10-30 second interval) for block tracking instead. Poll-based filter methods (`eth_newFilter`, `eth_getFilterChanges`, etc.) are also unsupported. Contact [support@radiustech.xyz](mailto:support@radiustech.xyz) for WebSocket access.

### WebSocket with reconnection

```typescript
const wsClient = createPublicClient({
  chain: radiusTestnet,
  transport: webSocket('wss://rpc.testnet.radiustech.xyz', {
    reconnect: {
      attempts: 5,
      delay: 2000,
    },
    keepAlive: {
      interval: 30_000, // Ping every 30 seconds
    },
  }),
});
```

## Complete example: payment monitor

Build a real-time payment tracker that watches for incoming token transfers:

```typescript
import {
  createPublicClient,
  http,
  formatEther,
  erc20Abi,
  type Log,
} from 'viem';

// Use the radiusTestnet chain definition from typescript-viem.md

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const SERVICE_ADDRESS = '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1';
const TOKEN_ADDRESS = '0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb';

interface PaymentRecord {
  from: string;
  amount: string;
  blockNumber: bigint;
  transactionHash: string;
  timestamp: Date;
}

const payments: PaymentRecord[] = [];

// Watch for incoming payments
const unwatch = publicClient.watchContractEvent({
  address: TOKEN_ADDRESS,
  abi: erc20Abi,
  eventName: 'Transfer',
  args: {
    to: SERVICE_ADDRESS,
  },
  onLogs: (logs) => {
    for (const log of logs) {
      const payment: PaymentRecord = {
        from: log.args.from!,
        amount: formatEther(log.args.value!),
        blockNumber: log.blockNumber!,
        transactionHash: log.transactionHash!,
        timestamp: new Date(),
      };

      payments.push(payment);
      console.log(`Payment received: ${payment.amount} USD from ${payment.from}`);
    }
  },
  onError: (error) => {
    console.error('Payment watch error:', error);
  },
});

// Graceful shutdown
process.on('SIGINT', () => {
  unwatch();
  console.log('Payment monitor stopped');
  console.log(`Total payments received: ${payments.length}`);
  process.exit(0);
});

console.log(`Monitoring payments to ${SERVICE_ADDRESS}...`);
```

## Best practices

### Always unwatch when done

Clean up subscriptions to prevent memory leaks:

```typescript
const unwatch = publicClient.watchBlockNumber({
  onBlockNumber: (blockNumber) => console.log(blockNumber),
});

// Later, when component unmounts or service stops
unwatch();
```

In React components, use the cleanup pattern:

```typescript
useEffect(() => {
  const unwatch = publicClient.watchContractEvent({ ... });
  return () => unwatch();
}, []);
```

### Handle errors gracefully

```typescript
publicClient.watchContractEvent({
  address: '0x...',
  abi: erc20Abi,
  eventName: 'Transfer',
  onLogs: (logs) => {
    // Process events
  },
  onError: (error) => {
    console.error('Watch error:', error);
    // Consider restarting the watcher after a delay
  },
});
```

### Use HTTP for polling, WebSocket for real-time

| Transport | Best for | Trade-off |
|-----------|----------|-----------|
| **HTTP** | Polling-based watching | More resilient, higher latency |
| **WebSocket** | Real-time event delivery | Lower latency, requires connection management and elevated RPC access |

### Batch reads with multicall

When fetching multiple independent contract reads, batch them:

```typescript
const [totalSupply, balance, decimals] = await Promise.all([
  publicClient.readContract({
    address: TOKEN_ADDRESS,
    abi: erc20Abi,
    functionName: 'totalSupply',
  }),
  publicClient.readContract({
    address: TOKEN_ADDRESS,
    abi: erc20Abi,
    functionName: 'balanceOf',
    args: [account.address],
  }),
  publicClient.readContract({
    address: TOKEN_ADDRESS,
    abi: erc20Abi,
    functionName: 'decimals',
  }),
]);
```

Or use Multicall3 for a single RPC call:

```typescript
const results = await publicClient.multicall({
  contracts: [
    { address: TOKEN_ADDRESS, abi: erc20Abi, functionName: 'totalSupply' },
    { address: TOKEN_ADDRESS, abi: erc20Abi, functionName: 'balanceOf', args: [account.address] },
    { address: TOKEN_ADDRESS, abi: erc20Abi, functionName: 'decimals' },
  ],
});
```

### Network configuration for events

| Setting | Value |
|---------|-------|
| **HTTP RPC** | `https://rpc.testnet.radiustech.xyz` |
| **WebSocket RPC** | `wss://rpc.testnet.radiustech.xyz` (requires elevated access) |
| **Chain ID** | `72344` (testnet) / `723` (mainnet) |
| **Supported subscriptions** | `logs` only (`newHeads` and `newPendingTransactions` not available) |