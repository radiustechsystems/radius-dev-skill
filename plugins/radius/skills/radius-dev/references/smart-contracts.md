# Smart Contract Deployment

## Overview

Radius is fully EVM-compatible. Deploy standard Solidity contracts using Foundry with no modifications. OpenZeppelin libraries work out of the box. Solidity Osaka hardfork is supported via Revm 33.1.0.

## Prerequisites

- A funded wallet
- Foundry installed

## Network configuration

| Setting | Value |
|---------|-------|
| **RPC URL** | `https://rpc.testnet.radiustech.xyz` |
| **Chain ID** | `72344` |
| **SBC Token** | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` (6 decimals) |

## Install Foundry

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

## Wallet setup (one-time)

Import your private key into Foundry's encrypted keystore so it never appears in shell history or process listings:

```bash
cast wallet import radius-deployer --interactive
# Enter private key: <paste key, input is hidden>
# Enter password:    <choose a password, input is hidden>
# `radius-deployer` keystore was saved successfully. Address: 0x...
```

The keystore is saved to `~/.foundry/keystores/radius-deployer`. You can list stored accounts with:

```bash
cast wallet list
```

Every `forge` and `cast` command below uses `--account radius-deployer` which prompts for the password at runtime. The account name is arbitrary — use whatever you like.

> **⚠️ Never use `--private-key` on the command line.** It exposes the key in shell history and `ps aux` output.

## Create a project

```bash
forge init my-project
cd my-project
```

## Example contract

```solidity
// src/Counter.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Counter {
    uint256 public count;

    function increment() public {
        count += 1;
    }

    function decrement() public {
        count -= 1;
    }
}
```

## Deploy with forge create

```bash
forge create src/Counter.sol:Counter \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --account radius-deployer
```

Output:

```
Deployer: 0xYourAddress
Deployed to: 0xContractAddress
Transaction hash: 0x...
```

### Deploy with constructor arguments

```bash
forge create src/Token.sol:Token \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --account radius-deployer \
  --constructor-args "My Token" "MTK" 18
```

## Deploy with forge script

For more complex deployments, use Foundry scripts:

```solidity
// script/Deploy.s.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/Counter.sol";

contract DeployScript is Script {
    function run() external {
        vm.startBroadcast();
        new Counter();
        vm.stopBroadcast();
    }
}
```

```bash
forge script script/Deploy.s.sol \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --account radius-deployer \
  --broadcast
```

## Verify deployment

After deployment, verify your contract is accessible:

```bash
# Check contract code exists at the address
cast code 0xYourContractAddress --rpc-url https://rpc.testnet.radiustech.xyz

# Call a view function
cast call 0xYourContractAddress "count()" --rpc-url https://rpc.testnet.radiustech.xyz
```

Radius has immediate finality. If the transaction succeeded, the contract is available instantly — no need to wait for confirmations.

## Interact with deployed contracts

### Using cast (Foundry CLI)

```bash
# Read state
cast call 0xContractAddress "count()" \
  --rpc-url https://rpc.testnet.radiustech.xyz

# Write state
cast send 0xContractAddress "increment()" \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --account radius-deployer
```

### Using viem (TypeScript)

```typescript
import { createPublicClient, createWalletClient, http, getContract } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { radiusTestnet } from './chain'; // See SKILL.md "Canonical chain definitions" to create this file

const account = privateKeyToAccount(process.env.PRIVATE_KEY as `0x${string}`);

const publicClient = createPublicClient({
  chain: radiusTestnet,
  transport: http(),
});

const walletClient = createWalletClient({
  account,
  chain: radiusTestnet,
  transport: http(),
});

const abi = [
  { name: 'count', type: 'function', inputs: [], outputs: [{ type: 'uint256' }], stateMutability: 'view' },
  { name: 'increment', type: 'function', inputs: [], outputs: [], stateMutability: 'nonpayable' },
] as const;

const CONTRACT_ADDRESS = '0x...' as const;

const contract = getContract({
  address: CONTRACT_ADDRESS,
  abi,
  client: { public: publicClient, wallet: walletClient },
});

// Read
const count = await contract.read.count();
console.log('Count:', count);

// Write
const hash = await contract.write.increment();
await publicClient.waitForTransactionReceipt({ hash });
```

## Deploy an ERC-20 token

Deploy a standard ERC-20 token using OpenZeppelin:

### Install OpenZeppelin

```bash
forge install OpenZeppelin/openzeppelin-contracts
```

### Token contract

```solidity
// src/Token.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract Token is ERC20 {
    constructor(string memory name, string memory symbol) ERC20(name, symbol) {
        _mint(msg.sender, 1_000_000 * 10**decimals());
    }
}
```

### Deploy

```bash
forge create src/Token.sol:Token \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --account radius-deployer \
  --constructor-args "My Token" "MTK"
```

## Testing with Foundry

### Write tests

```solidity
// test/Counter.t.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Counter.sol";

contract CounterTest is Test {
    Counter public counter;

    function setUp() public {
        counter = new Counter();
    }

    function test_InitialCount() public view {
        assertEq(counter.count(), 0);
    }

    function test_Increment() public {
        counter.increment();
        assertEq(counter.count(), 1);
    }

    function test_Decrement() public {
        counter.increment();
        counter.decrement();
        assertEq(counter.count(), 0);
    }

    function testFuzz_MultipleIncrements(uint8 n) public {
        for (uint8 i = 0; i < n; i++) {
            counter.increment();
        }
        assertEq(counter.count(), n);
    }
}
```

### Run tests

```bash
# Run all tests
forge test

# Run with verbosity for traces
forge test -vvv

# Run a specific test
forge test --match-test test_Increment

# Run with gas report
forge test --gas-report
```

### Fork testing against Radius Testnet

```bash
forge test --fork-url https://rpc.testnet.radiustech.xyz
```

## Gas and fees

Radius uses stablecoin fees instead of native gas:

- **Fee token**: RUSD
- **Gas price**: Fixed ~986M wei (~1 gwei) from `eth_gasPrice`. Use the transaction cost API for the most reliable value. `eth_maxPriorityFeePerGas` returns `0x0` (no priority fee bidding).
- **Fixed cost**: ~0.0001 USD per transaction
- **Failed transactions**: Do NOT charge gas (unlike Ethereum)

### Check fee token balance

```bash
cast call 0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb \
  "balanceOf(address)" 0xYourAddress \
  --rpc-url https://rpc.testnet.radiustech.xyz
```

## Solidity patterns for Radius

### What works unchanged

```solidity
// Standard ERC-20 interactions
IERC20(token).transfer(recipient, amount);

// Storage operations
mapping(address => uint256) balances;
balances[msg.sender] = 100;

// Events
emit Transfer(from, to, amount);

// All OpenZeppelin contracts
// All standard precompiles (0x01 - 0x0a)
```

### What to avoid

```solidity
// DON'T — native balance is not how Radius handles value
require(address(this).balance > 0);

// DO — use ERC-20 balance checks instead
require(IERC20(feeToken).balanceOf(address(this)) > 0);
```

### Receiving payments in contracts

Since Radius uses stablecoins, design payment flows around ERC-20 transfers rather than native ETH `payable` functions:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract PaymentReceiver {
    using SafeERC20 for IERC20;

    IERC20 public immutable paymentToken;
    address public owner;

    mapping(address => uint256) public deposits;

    event PaymentReceived(address indexed payer, uint256 amount);

    constructor(address _paymentToken) {
        paymentToken = IERC20(_paymentToken);
        owner = msg.sender;
    }

    function pay(uint256 amount) external {
        paymentToken.safeTransferFrom(msg.sender, address(this), amount);
        deposits[msg.sender] += amount;
        emit PaymentReceived(msg.sender, amount);
    }

    function withdraw() external {
        require(msg.sender == owner, "Not owner");
        uint256 balance = paymentToken.balanceOf(address(this));
        paymentToken.safeTransfer(owner, balance);
    }
}
```

## Common contract patterns

### Access control with OpenZeppelin

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

contract AdminContract is Ownable {
    uint256 public value;

    constructor() Ownable(msg.sender) {}

    function setValue(uint256 _value) external onlyOwner {
        value = _value;
    }
}
```

### Pausable contract

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract PausableService is Ownable, Pausable {
    constructor() Ownable(msg.sender) {}

    function criticalFunction() external whenNotPaused {
        // Business logic
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
```

### Using CREATE2 for deterministic addresses

Radius has the Arachnid Create2 Factory deployed at the canonical address:

```bash
# Arachnid Create2 Factory
0x4e59b44847b379578588920cA78FbF26c0B4956C

# CreateX (advanced: CREATE, CREATE2, CREATE3)
0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed
```

## Deployment checklist

1. **Fund wallet** from the faucet (see Radius "dripping faucet" skill)
2. **Verify RUSD balance** for fee payment
3. **Compile contracts** with `forge build`
4. **Run tests locally** with `forge test`
5. **Deploy** using `forge create` or `forge script`
6. **Verify** the contract code with `cast code <address>`
7. **Test interactions** on testnet with `cast call` / `cast send`

## Troubleshooting

### Transaction fails immediately

Check that your account has RUSD tokens for fees:

```bash
cast call 0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb \
  "balanceOf(address)" 0xYourAddress \
  --rpc-url https://rpc.testnet.radiustech.xyz
```

If balance is zero, visit the faucet (see Radius "dripping faucet" skill).

### Contract not found after deploy

Radius has immediate finality. If the deployment transaction succeeded, the contract exists instantly. Verify with:

```bash
cast code 0xContractAddress --rpc-url https://rpc.testnet.radiustech.xyz
```

If `cast code` returns `0x`, the deployment transaction likely reverted. Check the receipt:

```bash
cast receipt 0xTransactionHash --rpc-url https://rpc.testnet.radiustech.xyz
```

### Gas estimation issues

If gas estimation fails, try setting an explicit gas limit:

```bash
forge create src/Contract.sol:Contract \
  --rpc-url https://rpc.testnet.radiustech.xyz \
  --account radius-deployer \
  --gas-limit 3000000
```

### Constructor arguments encoding

If deployment with constructor args fails, verify the encoding:

```bash
# Encode arguments manually to debug
cast abi-encode "constructor(string,string,uint8)" "My Token" "MTK" 18
```

### Foundry configuration

Create `foundry.toml` with Radius defaults:

```toml
[profile.default]
src = "src"
out = "out"
libs = ["lib"]
gas_price = 1000000000
evm_version = "cancun"
via_ir = true

[profile.default.rpc_endpoints]
radius_testnet = "https://rpc.testnet.radiustech.xyz"
radius_mainnet = "https://rpc.radiustech.xyz"
```

| Setting | Purpose |
|---------|---------|
| `gas_price` | Matches Radius's fixed gas price (~1 gwei). Eliminates the need for `--gas-price` on every CLI command. |
| `evm_version` | Targets the EVM version Radius supports. |
| `via_ir` | Uses the IR-based code generator. Required for complex deploy scripts to avoid "Stack too deep" errors. |

Then deploy with the profile:

```bash
forge create src/Counter.sol:Counter \
  --rpc-url radius_testnet \
  --account radius-deployer \
  --broadcast
```

> Starting with Foundry 1.5.1, `forge create` defaults to dry-run mode. Add `--broadcast` to send the transaction on-chain.

## OpenZeppelin governance and timestamp clock mode

Radius block numbers are millisecond timestamps, not sequential heights. This breaks OpenZeppelin governance contracts that interpret block counts as time durations:

| Contract | Parameter | Ethereum interpretation | Radius interpretation | Fix |
|----------|-----------|------------------------|----------------------|-----|
| Governor | `votingDelay()` = 1 | ~12 seconds (1 block) | 1 millisecond | Use timestamp clock mode |
| Governor | `votingPeriod()` = 50400 | ~1 week | ~50 seconds | Use timestamp clock mode |
| TimelockController | Block-based delay | Predictable intervals | Millisecond timestamps | Use `block.timestamp` |
| Vesting | Block-based schedule | Predictable duration | Incorrect duration | Use `block.timestamp` |

Override the clock in OpenZeppelin v5:

```solidity
function CLOCK_MODE() public pure override returns (string memory) {
    return "mode=timestamp";
}

function clock() public view override returns (uint48) {
    return uint48(block.timestamp);
}
```

Apply these overrides to any contract inheriting Governor, TimelockController, or timestamp-sensitive vesting logic.
