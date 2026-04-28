# Transaction History

## Overview

Radius supports standard Ethereum-style transaction lookup by **hash** and by
**block/index**, but it does **not** expose a single JSON-RPC method that lists
all transactions for an address.

That means "show me every transaction for this wallet" splits into two
different problems:

- **Contract / token activity**: use `eth_getLogs` against known contract
  addresses and filter indexed fields such as `from` / `to`.
- **Full account history** including native transfers and arbitrary contract
  calls: use an **external indexer or explorer API**. Plain RPC is not enough.

## What the RPC can and cannot do

Useful RPC methods:

- `eth_getTransactionByHash` and `eth_getTransactionReceipt`: inspect a known
  transaction once you already have its hash.
- `eth_getTransactionByBlockNumberAndIndex` /
  `eth_getTransactionByBlockHashAndIndex`: enumerate transactions inside a known
  reconstructed block.
- `eth_getTransactionCount`: returns the nonce for an address. This tells you
  how many transactions were sent, **not** what they were.
- `eth_getLogs`: the best RPC tool for address-related history, but only for
  contract events on known contract addresses.

What is missing:

- No `eth_getTransactionsByAddress`
- No explorer-style address activity endpoint in JSON-RPC
- No practical RPC method for paginating complete address history across the
  chain without your own indexing layer

## Recommended guidance for the skill

When a user asks for transaction history for an address, the skill should
explicitly branch:

1. **If they want ERC-20 or contract event history**
   Use `eth_getLogs` with a concrete contract `address`, a bounded block range,
   and indexed topic filters such as `from: userAddress` and `to: userAddress`.

2. **If they want all wallet transactions**
   Explain that Radius RPC does not provide a single address-history method.
   Recommend an explorer / indexer API, or building an app-side indexer that
   stores transactions and receipts keyed by address.

3. **If they only know the wallet and need recent app activity**
   Narrow the scope to the app's own contracts and scan their events instead of
   attempting chain-wide history from RPC alone.

## ERC-20 transfer history via viem

This is the main pattern the skill should show for address-scoped history that
is feasible over RPC today.

```typescript
import {
  createPublicClient,
  erc20Abi,
  http,
  parseAbiItem,
  type PublicClient,
} from 'viem';

const transferEvent = parseAbiItem(
  'event Transfer(address indexed from, address indexed to, uint256 value)'
);

type TransferHistoryItem = {
  direction: 'in' | 'out';
  token: `0x${string}`;
  counterparty: `0x${string}`;
  value: bigint;
  blockNumber: bigint;
  transactionHash: `0x${string}`;
  logIndex: number;
};

async function getErc20TransferHistory(params: {
  publicClient: PublicClient;
  token: `0x${string}`;
  account: `0x${string}`;
  fromBlock: bigint;
  toBlock: bigint;
  chunkSize?: bigint;
}): Promise<TransferHistoryItem[]> {
  const {
    publicClient,
    token,
    account,
    fromBlock,
    toBlock,
    chunkSize = 1_000_000n,
  } = params;

  const items: TransferHistoryItem[] = [];

  for (let start = fromBlock; start <= toBlock; start += chunkSize) {
    const end = start + chunkSize - 1n > toBlock
      ? toBlock
      : start + chunkSize - 1n;

    const [incoming, outgoing] = await Promise.all([
      publicClient.getLogs({
        address: token,
        event: transferEvent,
        args: { to: account },
        fromBlock: start,
        toBlock: end,
      }),
      publicClient.getLogs({
        address: token,
        event: transferEvent,
        args: { from: account },
        fromBlock: start,
        toBlock: end,
      }),
    ]);

    for (const log of incoming) {
      items.push({
        direction: 'in',
        token,
        counterparty: log.args.from!,
        value: log.args.value!,
        blockNumber: log.blockNumber!,
        transactionHash: log.transactionHash!,
        logIndex: Number(log.logIndex!),
      });
    }

    for (const log of outgoing) {
      items.push({
        direction: 'out',
        token,
        counterparty: log.args.to!,
        value: log.args.value!,
        blockNumber: log.blockNumber!,
        transactionHash: log.transactionHash!,
        logIndex: Number(log.logIndex!),
      });
    }
  }

  return items.sort((a, b) => {
    if (a.blockNumber !== b.blockNumber) {
      return a.blockNumber > b.blockNumber ? -1 : 1;
    }
    return b.logIndex - a.logIndex;
  });
}
```

## Pagination notes

Radius-specific constraints matter here:

- `eth_getLogs` requires a contract `address`.
- Large queries must be chunked.
- Block numbers are millisecond timestamps, so range pagination is really
  **time-window pagination**.

Useful API shape for callers:

```typescript
type Page = {
  items: TransferHistoryItem[];
  nextFromBlock?: bigint;
};
```

A simple pattern is:

- Query newest window first.
- Return items sorted descending by `blockNumber`, then `logIndex`.
- Emit `nextFromBlock = oldestBlockInPage - 1n` when more history remains.

## Native transfers and full wallet history

For native RUSD transfers, arbitrary contract calls, and "everything this
address ever did", plain RPC is not enough.

Your realistic options are:

- Use a Radius explorer API if one is available for the environment.
- Build an app-owned indexer that ingests blocks / receipts and stores
  address-to-transaction relationships.
- Reduce the product requirement to the contracts your app controls and index
  only those events.

## Suggested wording to add to the skill

Use language this direct:

> Radius RPC does not provide a single method to list all transactions for an
> address. For token or contract activity, query `eth_getLogs` against known
> contract addresses and paginate by block-range windows. For complete wallet
> history, use an explorer/indexer API or maintain your own index.
