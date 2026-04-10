# Contract Deployment and Interaction Patterns

Workflows for deploying smart contracts and interacting with them on Radius, using the wallet libraries.

## Getting Contract Bytecode

### From Foundry Artifacts

Compile with `forge build`, then load the artifact:

```python
import json

def load_artifact(name: str) -> dict:
    """Load compiled contract artifact from Foundry's out/ directory."""
    with open(f"out/{name}.sol/{name}.json") as f:
        return json.load(f)

artifact = load_artifact("MyContract")
bytecode = artifact["bytecode"]["object"]   # Hex string starting with 0x
abi = artifact["abi"]                       # For TypeScript usage
```

### Pre-compiled Bytecode

For simple contracts, embed the bytecode directly. Example — a minimal Counter contract:

```python
# Solidity source:
#   uint256 public count;
#   function increment() public { count += 1; }
#   function getCount() public view returns (uint256) { return count; }

COUNTER_BYTECODE = (
    "0x6080604052348015600e575f5ffd5b506101778061001c5f395ff3fe60806040523480"
    "1561000f575f5ffd5b506004361061003f575f3560e01c806306661abd14610043578063"
    "a87d942c14610061578063d09de08a1461007f575b5f5ffd5b61004b610089565b604051"
    "61005891906100c8565b60405180910390f35b61006961008e565b60405161007691906100"
    "c8565b60405180910390f35b610087610096565b005b5f5481565b5f5f54905090565b6001"
    "5f5f8282546100a7919061010e565b92505081905550565b5f819050919050565b6100c281"
    "6100b0565b82525050565b5f6020820190506100db5f8301846100b9565b92915050565b7f"
    "4e487b71000000000000000000000000000000000000000000000000000000005f52601160"
    "045260245ffd5b5f610118826100b0565b9150610123836100b0565b92508282019050808211"
    "1561013b5761013a6100e1565b5b9291505056fea2646970667358221220df9004bd1eca7f"
    "9ccea721371446203e18a46b45aa1bb3de92a870337afe7b7564736f6c63430008210033"
)
```

## Deploy with Wallet Library

### Python — No Constructor Args

```python
from radius_wallet import RadiusWallet

wallet = RadiusWallet.from_env()
result = wallet.deploy_contract(COUNTER_BYTECODE)

print(f"Address: {result['address']}")
print(f"Explorer: {wallet.explorer_url(result['tx_hash'])}")
```

### Python — With Constructor Args

```python
from radius_wallet import RadiusWallet, SBC_ADDRESS

wallet = RadiusWallet.from_env()
artifact = load_artifact("PayPerQuery")

result = wallet.deploy_contract(
    bytecode=artifact["bytecode"]["object"],
    constructor_types=["address", "uint256"],
    constructor_args=[SBC_ADDRESS, 100_000],  # token address, price (0.1 SBC)
)
```

### TypeScript — No Constructor Args

```typescript
import { RadiusWallet } from "radius-wallet-ts";

const wallet = RadiusWallet.fromEnv();
const result = await wallet.deployContract(counterAbi, "0x608060..." as `0x${string}`);
console.log(`Address: ${result.address}`);
```

### TypeScript — With Constructor Args

```typescript
const artifact = JSON.parse(fs.readFileSync("out/PayPerQuery.sol/PayPerQuery.json", "utf8"));
const result = await wallet.deployContract(
  artifact.abi,
  artifact.bytecode.object as `0x${string}`,
  [SBC_ADDRESS, 100_000n],
);
```

## Deploy with Foundry CLI

```bash
# Simple deploy
forge create src/Counter.sol:Counter \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --private-key $RADIUS_PRIVATE_KEY

# With constructor args
forge create src/PayPerQuery.sol:PayPerQuery \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --private-key $RADIUS_PRIVATE_KEY \
  --constructor-args 0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb 100000
```

**Security note:** Prefer `--account <keystore>` over `--private-key` to avoid exposing the key in shell history. Create a keystore with `cast wallet new`.

## Read from Contracts

### Python (string-based function signatures)

```python
# No arguments
count = wallet.call_contract(
    address=contract_address,
    function_sig="getCount()",
    return_types=["uint256"],
)

# With arguments
balance = wallet.call_contract(
    address=contract_address,
    function_sig="balanceOf(address)",
    arg_types=["address"],
    args=["0xHolderAddress"],
    return_types=["uint256"],
)

# Multiple return values
name, symbol = wallet.call_contract(
    address=contract_address,
    function_sig="getInfo()",
    return_types=["string", "string"],
)
```

### TypeScript (typed ABI)

```typescript
const count = await wallet.readContract(contractAddress, abi, "getCount");
const balance = await wallet.readContract(contractAddress, abi, "balanceOf", ["0xHolder"]);
```

**Key difference:** Python uses string function signatures (e.g., `"balanceOf(address)"`) and manual type annotations. TypeScript uses a typed ABI and lets viem infer types.

## Write to Contracts

### Python

```python
# No arguments
tx_hash = wallet.send_contract_tx(contract_address, "increment()")
receipt = wallet.wait_for_tx(tx_hash)
assert wallet.tx_succeeded(receipt)

# With arguments
tx_hash = wallet.send_contract_tx(
    address=contract_address,
    function_sig="transfer(address,uint256)",
    arg_types=["address", "uint256"],
    args=["0xRecipient", 1_000_000],
)
receipt = wallet.wait_for_tx(tx_hash)

# With higher gas limit (for complex calls)
tx_hash = wallet.send_contract_tx(
    address=contract_address,
    function_sig="complexOperation(uint256)",
    arg_types=["uint256"],
    args=[42],
    gas=500_000,  # Default is 100,000
)
```

### TypeScript

```typescript
const txHash = await wallet.writeContract(contractAddress, abi, "increment");
const receipt = await wallet.waitForTx(txHash);

const txHash = await wallet.writeContract(
  contractAddress,
  abi,
  "transfer",
  ["0xRecipient", 1_000_000n],
);
```

## ERC-20 Approve + TransferFrom Pattern

Many agent contracts (escrow, bounty boards, pay-per-query) require depositing SBC tokens. This requires a two-step approval pattern:

1. **Approve** the contract to spend tokens on the wallet's behalf
2. **Call** the contract function that pulls tokens via `transferFrom`

### Python

```python
from radius_wallet import SBC_ADDRESS

# Step 1: Approve the contract to spend 10 SBC
amount_base = 10_000_000  # 10 SBC in base units (6 decimals)
tx = wallet.send_contract_tx(
    address=SBC_ADDRESS,
    function_sig="approve(address,uint256)",
    arg_types=["address", "uint256"],
    args=[contract_address, amount_base],
)
wallet.wait_for_tx(tx)

# Step 2: Call the contract function that pulls tokens
tx = wallet.send_contract_tx(
    address=contract_address,
    function_sig="deposit(uint256)",
    arg_types=["uint256"],
    args=[amount_base],
    gas=200_000,
)
receipt = wallet.wait_for_tx(tx)
assert wallet.tx_succeeded(receipt)
```

### TypeScript

```typescript
import { parseUnits } from "viem";
import { SBC_ADDRESS, SBC_DECIMALS, ERC20_ABI } from "radius-wallet-ts";

const amount = parseUnits("10", SBC_DECIMALS); // 10 SBC

// Step 1: Approve
const approveTx = await wallet.writeContract(
  SBC_ADDRESS,
  [...ERC20_ABI, { type: "function", name: "approve", inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }], outputs: [{ name: "", type: "bool" }], stateMutability: "nonpayable" }],
  "approve",
  [contractAddress, amount],
);
await wallet.waitForTx(approveTx);

// Step 2: Deposit
const depositTx = await wallet.writeContract(contractAddress, contractAbi, "deposit", [amount]);
await wallet.waitForTx(depositTx);
```

## Workshop Contracts

The `radius-agent-contracts` repository provides four Solidity contracts designed for agent-to-agent commerce on Radius. All use SBC for payments.

| Contract | Purpose | Key Functions |
|----------|---------|---------------|
| AgentEscrow | Two-party escrow for agent services | `createEscrow`, `complete`, `approve`, `dispute`, `refund` |
| BountyBoard | Open task marketplace for agents | `postBounty`, `claimBounty`, `submitWork`, `approveBounty` |
| PayPerQuery | Metered API billing | `deposit`, `query`, `withdraw`, `collectRevenue` |
| PaymentSplitter | Revenue sharing with proportional weights | `depositSBC`, `claimShare`, `pendingShare` |

**Example — PayPerQuery interaction:**

```python
from radius_wallet import RadiusWallet, SBC_ADDRESS

wallet = RadiusWallet.from_env()
ppq_address = "0xDeployedPayPerQueryAddress"

# Approve + deposit 5 SBC as a consumer
amount = 5_000_000  # 5 SBC in base units
wallet.send_contract_tx(SBC_ADDRESS, "approve(address,uint256)", ["address", "uint256"], [ppq_address, amount])
tx = wallet.send_contract_tx(ppq_address, "deposit(uint256)", ["uint256"], [amount], gas=200_000)
wallet.wait_for_tx(tx)

# Make a query (deducts the per-query fee)
query_hash = "0x" + "ab" * 32  # Your query identifier
tx = wallet.send_contract_tx(ppq_address, "query(bytes32)", ["bytes32"], [bytes.fromhex(query_hash[2:])])
receipt = wallet.wait_for_tx(tx)
```

Repository: `github.com/radiustechsystems/radius-agent-contracts`

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Deployment tx succeeds but no contract address | Bytecode is invalid or constructor reverts | Verify bytecode is correct; check constructor args match expected types |
| `gas required exceeds allowance` | Gas limit too low for deployment | Deployment default is 3,000,000; for interaction default is 100,000. Increase `gas` parameter for complex calls |
| `nonce too low` | Previous tx still pending or nonce collision | Wait for prior tx to confirm, or use a fresh nonce |
| Constructor arg encoding error | Mismatched types in `constructor_types` | Ensure types match Solidity exactly (e.g., `"uint256"` not `"uint"`, `"address[]"` for arrays) |
| Revert with no reason | Solidity `require` failed without a message | Check contract source for the failing require; verify preconditions (balances, approvals) |
| `execution reverted` on contract call | Calling a function that doesn't exist | Verify function signature matches exactly (no spaces, correct types) |
