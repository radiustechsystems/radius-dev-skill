# Core Workflows

Task-oriented Radius operations with general EVM tooling.

Default order:

1. `cast` (quick CLI actions)
2. `web3.py` (Python automation)
3. `viem` (TypeScript automation)

## Prerequisites

### Shared environment

```bash
export RADIUS_RPC_URL=https://rpc.testnet.radiustech.xyz
export RADIUS_CHAIN_ID=72344
export SBC_ADDRESS=0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb
export RADIUS_PRIVATE_KEY=0x...
```

### Tool setup

```bash
# cast / forge
foundryup

# Python fallback
pip install web3 eth-account

# TypeScript fallback
npm install viem
```

Security:

- Never print private keys.
- Never hardcode keys in source files.
- Prefer env vars or keystore-based signing.

## 1) Get Wallet Address and Balances

### cast

```bash
ADDR=$(cast wallet address --private-key "$RADIUS_PRIVATE_KEY")

# Native RUSD balance (wei)
cast balance "$ADDR" --rpc-url "$RADIUS_RPC_URL"

# SBC ERC-20 balance (base units, 6 decimals)
cast call "$SBC_ADDRESS" "balanceOf(address)(uint256)" "$ADDR" --rpc-url "$RADIUS_RPC_URL"
```

### web3.py

```python
import os
from web3 import Web3
from eth_account import Account

rpc = "https://rpc.testnet.radiustech.xyz"
w3 = Web3(Web3.HTTPProvider(rpc))
acct = Account.from_key(os.environ["RADIUS_PRIVATE_KEY"])
address = acct.address

sbc_abi = [{
    "name": "balanceOf",
    "type": "function",
    "stateMutability": "view",
    "inputs": [{"name": "owner", "type": "address"}],
    "outputs": [{"name": "", "type": "uint256"}],
}]

token = w3.eth.contract(address="0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb", abi=sbc_abi)

rusd_wei = w3.eth.get_balance(address)
sbc_base = token.functions.balanceOf(address).call()

print(address)
print(rusd_wei)   # divide by 1e18 for display
print(sbc_base)   # divide by 1e6 for display
```

### viem

```typescript
import { createPublicClient, defineChain, http, getAddress } from "viem";

const radiusTestnet = defineChain({
  id: 72344,
  name: "Radius Testnet",
  nativeCurrency: { name: "RUSD", symbol: "RUSD", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc.testnet.radiustech.xyz"] } },
});

const publicClient = createPublicClient({ chain: radiusTestnet, transport: http() });
const address = getAddress("0xYourAddress");

const sbcAbi = [{
  type: "function",
  name: "balanceOf",
  stateMutability: "view",
  inputs: [{ name: "owner", type: "address" }],
  outputs: [{ name: "", type: "uint256" }],
}] as const;

const rusdWei = await publicClient.getBalance({ address });
const sbcBase = await publicClient.readContract({
  address: "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb",
  abi: sbcAbi,
  functionName: "balanceOf",
  args: [address],
});
```

## 2) Send SBC (ERC-20) and Verify

### cast

```bash
# 0.5 SBC = 500000 base units (6 decimals)
TX_HASH=$(cast send "$SBC_ADDRESS" \
  "transfer(address,uint256)" \
  0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68 \
  500000 \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$TX_HASH" --rpc-url "$RADIUS_RPC_URL"
```

### web3.py

```python
import os
from web3 import Web3
from eth_account import Account

rpc = "https://rpc.testnet.radiustech.xyz"
private_key = os.environ["RADIUS_PRIVATE_KEY"]
recipient = "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68"
amount_base = 500_000  # 0.5 SBC

w3 = Web3(Web3.HTTPProvider(rpc))
acct = Account.from_key(private_key)

abi = [{
    "name": "transfer",
    "type": "function",
    "stateMutability": "nonpayable",
    "inputs": [
        {"name": "to", "type": "address"},
        {"name": "amount", "type": "uint256"},
    ],
    "outputs": [{"name": "", "type": "bool"}],
}]

token = w3.eth.contract(address="0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb", abi=abi)
nonce = w3.eth.get_transaction_count(acct.address)

tx = token.functions.transfer(recipient, amount_base).build_transaction({
    "chainId": 72344,
    "nonce": nonce,
    "gas": 100000,
    "gasPrice": w3.eth.gas_price,
})

signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
print(receipt.status)
```

### viem

```typescript
import {
  createPublicClient,
  createWalletClient,
  defineChain,
  http,
  parseUnits,
  privateKeyToAccount,
} from "viem";

const chain = defineChain({
  id: 72344,
  name: "Radius Testnet",
  nativeCurrency: { name: "RUSD", symbol: "RUSD", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc.testnet.radiustech.xyz"] } },
});

const privateKey = process.env.RADIUS_PRIVATE_KEY as `0x${string}`;
const account = privateKeyToAccount(privateKey);
const publicClient = createPublicClient({ chain, transport: http() });
const walletClient = createWalletClient({ account, chain, transport: http() });

const erc20Abi = [{
  type: "function",
  name: "transfer",
  stateMutability: "nonpayable",
  inputs: [
    { name: "to", type: "address" },
    { name: "amount", type: "uint256" },
  ],
  outputs: [{ name: "", type: "bool" }],
}] as const;

const txHash = await walletClient.writeContract({
  address: "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb",
  abi: erc20Abi,
  functionName: "transfer",
  args: ["0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68", parseUnits("0.5", 6)],
});

const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash });
```

## 3) Send Native RUSD and Verify

### cast

```bash
# 0.001 RUSD = 1000000000000000 wei
TX_HASH=$(cast send 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68 \
  --value 1000000000000000 \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$TX_HASH" --rpc-url "$RADIUS_RPC_URL"
```

### web3.py

```python
import os
from web3 import Web3
from eth_account import Account

w3 = Web3(Web3.HTTPProvider("https://rpc.testnet.radiustech.xyz"))
acct = Account.from_key(os.environ["RADIUS_PRIVATE_KEY"])

tx = {
    "to": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
    "value": 1_000_000_000_000_000,  # 0.001 RUSD in wei
    "nonce": w3.eth.get_transaction_count(acct.address),
    "gas": 21000,
    "gasPrice": w3.eth.gas_price,
    "chainId": 72344,
}

signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
print(receipt.status)
```

### viem

```typescript
import {
  createPublicClient,
  createWalletClient,
  defineChain,
  http,
  parseEther,
  privateKeyToAccount,
} from "viem";

const chain = defineChain({
  id: 72344,
  name: "Radius Testnet",
  nativeCurrency: { name: "RUSD", symbol: "RUSD", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc.testnet.radiustech.xyz"] } },
});

const privateKey = process.env.RADIUS_PRIVATE_KEY as `0x${string}`;
const account = privateKeyToAccount(privateKey);
const publicClient = createPublicClient({ chain, transport: http() });
const walletClient = createWalletClient({ account, chain, transport: http() });

const txHash = await walletClient.sendTransaction({
  to: "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
  value: parseEther("0.001"),
});

const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash });
```

## 4) Check Transaction Status and Explorer URL

### cast

```bash
cast receipt 0xTxHash --rpc-url "$RADIUS_RPC_URL"
# status=1 success
# status=0 revert
```

Explorer URLs:

```text
https://testnet.radiustech.xyz/tx/<tx_hash>
https://network.radiustech.xyz/tx/<tx_hash>
```

### web3.py

```python
receipt = w3.eth.get_transaction_receipt("0xTxHash")
success = receipt["status"] == 1
```

### viem

```typescript
const receipt = await publicClient.getTransactionReceipt({ hash: "0xTxHash" });
const success = receipt.status === "success";
```

## 5) Deploy Bytecode, Then Read/Write Contract

### cast

```bash
# Deploy
BYTECODE=0x608060...
DEPLOY_TX=$(cast send --create "$BYTECODE" --rpc-url "$RADIUS_RPC_URL" --private-key "$RADIUS_PRIVATE_KEY")

# Read
cast call 0xContractAddress "getCount()(uint256)" --rpc-url "$RADIUS_RPC_URL"

# Write
WRITE_TX=$(cast send 0xContractAddress "increment()" --rpc-url "$RADIUS_RPC_URL" --private-key "$RADIUS_PRIVATE_KEY")
cast receipt "$WRITE_TX" --rpc-url "$RADIUS_RPC_URL"
```

### web3.py

```python
contract = w3.eth.contract(abi=counter_abi, bytecode=counter_bytecode)
nonce = w3.eth.get_transaction_count(acct.address)

deploy_tx = contract.constructor().build_transaction({
    "chainId": 72344,
    "nonce": nonce,
    "gas": 3_000_000,
    "gasPrice": w3.eth.gas_price,
})

deploy_signed = acct.sign_transaction(deploy_tx)
deploy_hash = w3.eth.send_raw_transaction(deploy_signed.raw_transaction)
deploy_receipt = w3.eth.wait_for_transaction_receipt(deploy_hash)
contract_addr = deploy_receipt.contractAddress

instance = w3.eth.contract(address=contract_addr, abi=counter_abi)
initial = instance.functions.getCount().call()

write_tx = instance.functions.increment().build_transaction({
    "chainId": 72344,
    "nonce": w3.eth.get_transaction_count(acct.address),
    "gas": 100_000,
    "gasPrice": w3.eth.gas_price,
})

write_signed = acct.sign_transaction(write_tx)
write_hash = w3.eth.send_raw_transaction(write_signed.raw_transaction)
w3.eth.wait_for_transaction_receipt(write_hash)
```

### viem

```typescript
const deployHash = await walletClient.deployContract({
  abi: counterAbi,
  bytecode: counterBytecode,
});

const deployReceipt = await publicClient.waitForTransactionReceipt({ hash: deployHash });
const contractAddress = deployReceipt.contractAddress as `0x${string}`;

const before = await publicClient.readContract({
  address: contractAddress,
  abi: counterAbi,
  functionName: "getCount",
});

const writeHash = await walletClient.writeContract({
  address: contractAddress,
  abi: counterAbi,
  functionName: "increment",
});

await publicClient.waitForTransactionReceipt({ hash: writeHash });
```

## Faucet

Use the **dripping-faucet** skill for faucet requests and signed fallback behavior.

## Raw JSON-RPC Fallback (Last Resort)

Only use raw JSON-RPC when `cast`, `web3.py`, and `viem` are unavailable.

```bash
curl -s "$RADIUS_RPC_URL" -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0",
  "id":1,
  "method":"eth_getTransactionReceipt",
  "params":["0xTxHash"]
}'
```
