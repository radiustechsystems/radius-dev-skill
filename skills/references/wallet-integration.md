# Wallet Integration

## Overview

Radius Network works with all major Ethereum-compatible wallets through the EIP-1193 standard. The same integration code works across different wallet implementations.

**Supported wallets:**
- **MetaMask** — Industry standard browser extension
- **Rainbow** — Mobile-first wallet with excellent UX
- **WalletConnect** — QR-code based connection for mobile wallets
- **Coinbase Wallet** — Native web3 support
- **Trust Wallet** — Mobile wallet with dApp browser
- **Any EIP-1193 provider** — Direct integration via `window.ethereum`

## Add Radius Network to wallets

Before users can transact, they need the Radius Network configured in their wallet. Add it programmatically using `wallet_addEthereumChain`.

### Network configuration object

```javascript
const radiusTestnet = {
  chainId: '0x11a98', // 72344 in decimal
  chainName: 'Radius Testnet',
  nativeCurrency: {
    name: 'RUSD',
    symbol: 'RUSD',
    decimals: 18,
  },
  rpcUrls: ['https://rpc.testnet.radiustech.xyz'],
  blockExplorerUrls: ['https://testnet.radiustech.xyz'],
};
```

### Add network to MetaMask

```javascript
async function addRadiusNetwork() {
  if (!window.ethereum) {
    console.error('MetaMask not detected');
    return;
  }

  try {
    await window.ethereum.request({
      method: 'wallet_addEthereumChain',
      params: [radiusTestnet],
    });
    console.log('Radius Network added successfully');
  } catch (error) {
    if (error.code === 4001) {
      console.log('User rejected network addition');
    } else {
      console.error('Failed to add network:', error);
    }
  }
}
```

Call on page load or from an "Add Network" button. If the network already exists, the wallet switches to it.

## wagmi (recommended for React)

[wagmi](https://wagmi.sh) is the recommended approach for wallet integration in React applications. Define the Radius chain with viem's `defineChain` and pass it to wagmi's `createConfig`.

### Installation

```bash
pnpm add wagmi viem @tanstack/react-query
```

### Configure wagmi for Radius

```typescript
import { WagmiProvider, createConfig, http } from 'wagmi';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { defineChain } from 'viem';
import { injected } from 'wagmi/connectors';

// Define Radius Testnet (see typescript-viem.md for the full chain definition)
const radiusTestnet = defineChain({
  id: 72344,
  name: 'Radius Testnet',
  nativeCurrency: { decimals: 18, name: 'RUSD', symbol: 'RUSD' },
  rpcUrls: { default: { http: ['https://rpc.testnet.radiustech.xyz'] } },
  blockExplorers: {
    default: { name: 'Radius Explorer', url: 'https://testnet.radiustech.xyz' },
  },
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

const queryClient = new QueryClient();

export function App({ children }) {
  return (
    <WagmiProvider config={config}>
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    </WagmiProvider>
  );
}
```

### Connect wallet

```typescript
import { useConnect, useAccount, useDisconnect } from 'wagmi';

function ConnectButton() {
  const { connect, connectors, isPending } = useConnect();
  const { address, isConnected } = useAccount();
  const { disconnect } = useDisconnect();

  if (isConnected) {
    return (
      <div>
        <p>Connected: {address}</p>
        <button onClick={() => disconnect()}>Disconnect</button>
      </div>
    );
  }

  return (
    <div>
      {connectors.map((connector) => (
        <button
          key={connector.id}
          onClick={() => connect({ connector })}
          disabled={isPending}
        >
          {connector.name}
        </button>
      ))}
    </div>
  );
}
```

### Send a transaction

```typescript
import { useSendTransaction, useWaitForTransactionReceipt } from 'wagmi';
import { parseEther } from 'viem';

function SendTransaction() {
  const { sendTransaction, data: hash, isPending, error } = useSendTransaction();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({ hash });

  return (
    <div>
      <button
        onClick={() => sendTransaction({
          to: '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1',
          value: parseEther('0.1'),
        })}
        disabled={isPending}
      >
        {isPending ? 'Sending...' : 'Send 0.1 USD'}
      </button>

      {hash && <p>Hash: {hash}</p>}
      {isConfirming && <p>Confirming...</p>}
      {isSuccess && <p>Transaction confirmed!</p>}
      {error && <p>Error: {error.message}</p>}
    </div>
  );
}
```

### Read contract data

```typescript
import { useReadContract } from 'wagmi';
import { erc20Abi } from 'viem';

function TokenBalance({ address }: { address: `0x${string}` }) {
  const { data: balance, isLoading } = useReadContract({
    address: '0xF966020a30946A64B39E2e243049036367590858',
    abi: erc20Abi,
    functionName: 'balanceOf',
    args: [address],
  });

  if (isLoading) return <p>Loading...</p>;

  return <p>Balance: {balance?.toString()}</p>;
}
```

### Write to a contract

```typescript
import { useWriteContract, useWaitForTransactionReceipt } from 'wagmi';
import { erc20Abi, parseEther } from 'viem';

function TransferToken() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const { isSuccess } = useWaitForTransactionReceipt({ hash });

  const handleTransfer = () => {
    writeContract({
      address: '0xF966020a30946A64B39E2e243049036367590858',
      abi: erc20Abi,
      functionName: 'transfer',
      args: ['0x70997970C51812dc3A010C7d01b50e0d17dc79C8', parseEther('1')],
    });
  };

  return (
    <div>
      <button onClick={handleTransfer} disabled={isPending}>
        {isPending ? 'Transferring...' : 'Transfer 1 Token'}
      </button>
      {isSuccess && <p>Transfer confirmed!</p>}
    </div>
  );
}
```

## viem directly (non-React)

For non-React applications or when you need more control, use viem directly.

### Connect wallet via window.ethereum

```typescript
import { createWalletClient, createPublicClient, custom, http, defineChain } from 'viem';

// Use the radiusTestnet chain definition from the wagmi section above
// (or define it inline — see typescript-viem.md for the full pattern)

async function connectWallet() {
  if (!window.ethereum) {
    throw new Error('MetaMask not installed');
  }

  // Create wallet client for signing
  const walletClient = createWalletClient({
    chain: radiusTestnet,
    transport: custom(window.ethereum),
  });

  // Create public client for reading
  const publicClient = createPublicClient({
    chain: radiusTestnet,
    transport: http(),
  });

  // Request account access
  const [address] = await walletClient.requestAddresses();
  console.log('Connected address:', address);

  return { walletClient, publicClient, address };
}
```

### Send a transaction with viem

```typescript
import { parseEther } from 'viem';

async function sendTransaction(walletClient, publicClient, address, to, amount) {
  try {
    const hash = await walletClient.sendTransaction({
      account: address,
      to,
      value: parseEther(amount),
    });

    console.log('Transaction sent:', hash);

    // Wait for receipt (usually instant on Radius)
    const receipt = await publicClient.waitForTransactionReceipt({ hash });

    if (receipt.status === 'success') {
      console.log('Transaction confirmed');
      return receipt;
    } else {
      console.error('Transaction reverted');
      return null;
    }
  } catch (error) {
    console.error('Transaction error:', error);
    throw error;
  }
}
```

## Transaction characteristics on Radius

Key differences from Ethereum that affect wallet integration:

- **Stablecoin fees** — Gas is paid in stablecoins via the Turnstile mechanism. Users do not need to hold a separate gas token.
- **Immediate finality** — Transactions finalize in the next block (~200ms). No need to wait for multiple confirmations.
- **Standard gas estimation** — Wallets estimate gas normally; Radius handles fee conversion behind the scenes.
- **No reorgs** — Once confirmed, a transaction cannot be reversed by chain reorganization.

### Connection flow

1. Check if `window.ethereum` exists (wallet is installed)
2. Call `eth_requestAccounts` to prompt user for permission
3. Retrieve the user's primary address
4. Store the address for subsequent transactions

## Error handling

### Handle common wallet errors

```typescript
async function handleWalletError(error) {
  // User rejected the request
  if (error.code === 4001) {
    return { success: false, reason: 'rejected' };
  }

  // Wallet not installed
  if (error.code === -32603 || error.message?.includes('not defined')) {
    return { success: false, reason: 'not_installed' };
  }

  // Network not added
  if (error.code === 4902) {
    return { success: false, reason: 'wrong_network' };
  }

  // Insufficient balance
  if (error.message?.includes('insufficient funds')) {
    return { success: false, reason: 'insufficient_balance' };
  }

  // Transaction reverted
  if (error.message?.includes('reverted')) {
    return { success: false, reason: 'reverted' };
  }

  return { success: false, reason: 'unknown', error };
}
```

### Common error scenarios

| Error Code | Cause | Solution |
|-----------|-------|----------|
| `4001` | User rejected request | Inform user and offer retry |
| `4902` | Network not added | Call `wallet_addEthereumChain` |
| `Insufficient funds` | Balance too low | Check balance before sending |
| `Already pending` | Duplicate tx | Debounce the submit button |
| `Reverted` | Contract logic failed | Check contract conditions |

## Complete React example

Full component with wallet connect and transaction sending:

```typescript
import { useState } from 'react';
import { createWalletClient, createPublicClient, custom, http, parseEther, defineChain } from 'viem';

// Use the radiusTestnet chain definition from the wagmi section above

export default function WalletApp() {
  const [address, setAddress] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [txHash, setTxHash] = useState<string | null>(null);

  const connectWallet = async () => {
    try {
      setLoading(true);

      const walletClient = createWalletClient({
        chain: radiusTestnet,
        transport: custom(window.ethereum!),
      });

      const [addr] = await walletClient.requestAddresses();
      setAddress(addr);
    } catch (error) {
      console.error('Connection failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const sendUsd = async () => {
    if (!address) return;

    try {
      setLoading(true);

      const walletClient = createWalletClient({
        chain: radiusTestnet,
        transport: custom(window.ethereum!),
      });

      const publicClient = createPublicClient({
        chain: radiusTestnet,
        transport: http(),
      });

      const hash = await walletClient.sendTransaction({
        account: address as `0x${string}`,
        to: '0x742d35Cc6634C0532925a3b844Bc9e7595f7E9F1',
        value: parseEther('0.1'),
      });

      setTxHash(hash);

      const receipt = await publicClient.waitForTransactionReceipt({ hash });
      console.log('Status:', receipt.status);
    } catch (error) {
      console.error('Transaction failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {address ? (
        <div>
          <p>Connected: {address}</p>
          {txHash && <p>Last TX: {txHash}</p>}
          <button onClick={sendUsd} disabled={loading}>
            {loading ? 'Sending...' : 'Send 0.1 USD'}
          </button>
        </div>
      ) : (
        <button onClick={connectWallet} disabled={loading}>
          {loading ? 'Connecting...' : 'Connect Wallet'}
        </button>
      )}
    </div>
  );
}
```

## Best practices

1. **Show loading states** — Disable UI elements while waiting for wallet response or transaction confirmation
2. **Display transaction hash** — Let users view progress on the [block explorer](https://testnet.radiustech.xyz)
3. **Handle disconnection** — Listen for `disconnect` and `accountsChanged` events and reset state
4. **Validate addresses** — Ensure addresses are valid before constructing transactions
5. **Debounce transactions** — Prevent accidental duplicate submissions by disabling the button after click
6. **Guide network setup** — If the user is on the wrong network, prompt them to add Radius via `wallet_addEthereumChain`
7. **Show clear errors** — Map error codes to human-readable messages rather than showing raw error objects
8. **Test on testnet first** — Always verify the complete wallet flow on Radius Testnet before going live