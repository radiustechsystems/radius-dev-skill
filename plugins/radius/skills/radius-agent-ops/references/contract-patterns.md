# Contract Deployment and Interaction Patterns

Practical patterns for deploying and interacting with contracts on Radius using general EVM tooling.

## Defaults

- Primary: `cast`
- Python fallback: `web3.py`
- TypeScript fallback: `viem`

## Core Constants

```text
Testnet RPC: https://rpc.testnet.radiustech.xyz
Mainnet RPC: https://rpc.radiustech.xyz
Testnet Chain ID: 72344
Mainnet Chain ID: 723487
SBC token: 0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb
SBC decimals: 6
```

## Get Bytecode and ABI

### From Foundry artifacts

```bash
forge build
```

```python
import json

with open("out/Counter.sol/Counter.json") as f:
    artifact = json.load(f)

bytecode = artifact["bytecode"]["object"]
abi = artifact["abi"]
```

## Deploy Contract

### cast (default)

```bash
BYTECODE=0x608060...
DEPLOY_TX=$(cast send --create "$BYTECODE" \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$DEPLOY_TX" --rpc-url "$RADIUS_RPC_URL"
```

### forge (source-based deployment)

```bash
forge create src/Counter.sol:Counter \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY"
```

For constructor args with source deployment:

```bash
forge create src/PayPerQuery.sol:PayPerQuery \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY" \
  --constructor-args 0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb 100000
```

### web3.py fallback

```python
import os
from web3 import Web3
from eth_account import Account

w3 = Web3(Web3.HTTPProvider("https://rpc.testnet.radiustech.xyz"))
acct = Account.from_key(os.environ["RADIUS_PRIVATE_KEY"])

contract = w3.eth.contract(abi=abi, bytecode=bytecode)
nonce = w3.eth.get_transaction_count(acct.address)

tx = contract.constructor().build_transaction({
    "chainId": 72344,
    "nonce": nonce,
    "gas": 3_000_000,
    "gasPrice": w3.eth.gas_price,
})

signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
contract_address = receipt.contractAddress
```

### viem fallback

```typescript
const deployHash = await walletClient.deployContract({
  abi: contractAbi,
  bytecode: contractBytecode,
  args: [],
});

const deployReceipt = await publicClient.waitForTransactionReceipt({ hash: deployHash });
const contractAddress = deployReceipt.contractAddress as `0x${string}`;
```

## Read and Write Contract Functions

### cast

```bash
# Read
cast call 0xContractAddress "getCount()(uint256)" --rpc-url "$RADIUS_RPC_URL"

# Write
WRITE_TX=$(cast send 0xContractAddress "increment()" \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$WRITE_TX" --rpc-url "$RADIUS_RPC_URL"
```

### web3.py

```python
instance = w3.eth.contract(address=contract_address, abi=abi)

count_before = instance.functions.getCount().call()

tx = instance.functions.increment().build_transaction({
    "chainId": 72344,
    "nonce": w3.eth.get_transaction_count(acct.address),
    "gas": 100_000,
    "gasPrice": w3.eth.gas_price,
})

signed = acct.sign_transaction(tx)
write_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
write_receipt = w3.eth.wait_for_transaction_receipt(write_hash)
```

### viem

```typescript
const countBefore = await publicClient.readContract({
  address: contractAddress,
  abi: contractAbi,
  functionName: "getCount",
});

const writeHash = await walletClient.writeContract({
  address: contractAddress,
  abi: contractAbi,
  functionName: "increment",
});

await publicClient.waitForTransactionReceipt({ hash: writeHash });
```

## ERC-20 Approve + TransferFrom Pattern

Use this for escrow, bounty, and pay-per-query style contracts.

### cast

```bash
# 10 SBC = 10000000 base units
APPROVE_TX=$(cast send 0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb \
  "approve(address,uint256)" \
  0xContractAddress \
  10000000 \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$APPROVE_TX" --rpc-url "$RADIUS_RPC_URL"

DEPOSIT_TX=$(cast send 0xContractAddress \
  "deposit(uint256)" \
  10000000 \
  --rpc-url "$RADIUS_RPC_URL" \
  --private-key "$RADIUS_PRIVATE_KEY")

cast receipt "$DEPOSIT_TX" --rpc-url "$RADIUS_RPC_URL"
```

### web3.py

```python
sbc = w3.eth.contract(address="0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb", abi=erc20_abi)
app = w3.eth.contract(address=contract_address, abi=app_abi)
amount = 10_000_000

approve_tx = sbc.functions.approve(contract_address, amount).build_transaction({...})
# sign, send, wait receipt

deposit_tx = app.functions.deposit(amount).build_transaction({...})
# sign, send, wait receipt
```

### viem

```typescript
const amount = parseUnits("10", 6);

const approveHash = await walletClient.writeContract({
  address: "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb",
  abi: erc20Abi,
  functionName: "approve",
  args: [contractAddress, amount],
});
await publicClient.waitForTransactionReceipt({ hash: approveHash });

const depositHash = await walletClient.writeContract({
  address: contractAddress,
  abi: appAbi,
  functionName: "deposit",
  args: [amount],
});
await publicClient.waitForTransactionReceipt({ hash: depositHash });
```

## Workshop Contracts

`radius-agent-contracts` includes:

- `AgentEscrow`
- `BountyBoard`
- `PayPerQuery`
- `PaymentSplitter`

Repository: `github.com/radiustechsystems/radius-agent-contracts`

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Deployment succeeds but no contract address visible | Reading wrong output field | Inspect receipt for `contractAddress` |
| `gas required exceeds allowance` | Gas limit too low | Raise gas limit for deploy/write |
| `nonce too low` | Pending tx or nonce reuse | Wait for pending tx, then retry with fresh nonce |
| Revert on write | Preconditions not met | Check approvals, balances, and contract requirements |
| Unexpected amount math | Decimal mismatch | SBC is 6 decimals, RUSD is 18 |
| Key exposure risk | Unsafe signing flow | Use env vars/keystore; never paste keys into commands |
