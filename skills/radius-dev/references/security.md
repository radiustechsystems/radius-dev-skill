# Security Checklist (Smart Contract + Client)

## Core Principle

Assume the attacker controls:
- Every parameter passed to your contract functions
- Transaction ordering and timing
- External contract behavior (via composability)
- Client-side state and callbacks

Radius provides instant finality and eliminates reorgs, but standard EVM smart contract security remains critical.

---

## Smart Contract Vulnerability Categories

### 1. Reentrancy Attacks

**Risk**: An external call to an untrusted contract allows the callee to re-enter your contract before state updates complete, draining funds or corrupting state.

**Attack**: Attacker deploys a contract whose `receive()` or fallback function calls back into your vulnerable `withdraw()` function before the balance is decremented.

**Prevention — Checks-Effects-Interactions (CEI) pattern**:

```solidity
// BAD — state update after external call
function withdraw(uint256 amount) external {
    require(balances[msg.sender] >= amount);
    (bool success, ) = msg.sender.call{value: amount}("");
    require(success);
    balances[msg.sender] -= amount; // Too late!
}

// GOOD — state update before external call
function withdraw(uint256 amount) external {
    require(balances[msg.sender] >= amount);
    balances[msg.sender] -= amount; // Update first
    (bool success, ) = msg.sender.call{value: amount}("");
    require(success);
}
```

**Prevention — OpenZeppelin ReentrancyGuard**:

```solidity
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract Vault is ReentrancyGuard {
    function withdraw(uint256 amount) external nonReentrant {
        require(balances[msg.sender] >= amount);
        balances[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success);
    }
}
```

**Recommendation**: Use `nonReentrant` on all functions that perform external calls or token transfers. Apply the CEI pattern even when using the guard.

---

### 2. Access Control Issues

**Risk**: Critical functions (minting, pausing, upgrading, withdrawing) lack proper access restrictions, allowing anyone to call them.

**Attack**: Attacker calls an unprotected admin function to drain funds, mint tokens, or change ownership.

**Prevention — Ownable**:

```solidity
import "@openzeppelin/contracts/access/Ownable.sol";

contract AdminContract is Ownable {
    constructor() Ownable(msg.sender) {}

    function emergencyWithdraw() external onlyOwner {
        // Only contract owner can call
    }
}
```

**Prevention — Role-based access (AccessControl)**:

```solidity
import "@openzeppelin/contracts/access/AccessControl.sol";

contract ManagedContract is AccessControl {
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    constructor() {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ADMIN_ROLE, msg.sender);
    }

    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        // Only minters can call
    }

    function pause() external onlyRole(ADMIN_ROLE) {
        // Only admins can call
    }
}
```

---

### 3. Integer Overflow / Underflow

**Risk**: Arithmetic operations wrap around, producing unexpected results that bypass balance checks or create tokens from nothing.

**Prevention**: Solidity 0.8+ has built-in overflow/underflow checks that revert on overflow by default. If you use `unchecked` blocks for gas optimization, be absolutely certain the math cannot overflow:

```solidity
// Safe by default in Solidity 0.8+
uint256 result = a + b; // Reverts on overflow

// Only use unchecked when you can prove safety
unchecked {
    // ONLY when you know i < array.length
    uint256 index = i + 1;
}
```

**Warning**: Never use `unchecked` around user-supplied values or financial calculations.

---

### 4. Unchecked External Calls

**Risk**: Low-level calls (`.call`, `.delegatecall`, `.staticcall`) return a boolean success flag. If you don't check it, failed calls are silently ignored.

**Attack**: A transfer fails silently, but your contract records it as successful, leading to accounting discrepancies.

**Prevention**:

```solidity
// BAD — ignoring return value
payable(recipient).call{value: amount}("");

// GOOD — checking return value
(bool success, ) = payable(recipient).call{value: amount}("");
require(success, "Transfer failed");

// BEST — use SafeERC20 for token transfers
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

using SafeERC20 for IERC20;
token.safeTransfer(recipient, amount);
```

---

### 5. Front-Running

**Risk**: An observer sees your pending transaction and submits a competing transaction with a higher gas price to execute first, profiting at your expense.

**Radius-specific note**: Radius does not have a traditional public mempool, and its per-shard Raft consensus model significantly reduces traditional front-running vectors. However, if your application interacts with external systems or has observable state changes, consider these mitigations:

**Prevention**:

- **Commit-reveal schemes** — Split actions into commit (hashed intent) and reveal (actual parameters) phases
- **Deadline parameters** — Allow users to specify a deadline after which their transaction should revert
- **Slippage protection** — For swap-like operations, let users specify minimum acceptable output amounts

```solidity
function swap(
    uint256 amountIn,
    uint256 minAmountOut, // Slippage protection
    uint256 deadline       // Time protection
) external {
    require(block.timestamp <= deadline, "Transaction expired");
    uint256 amountOut = calculateOutput(amountIn);
    require(amountOut >= minAmountOut, "Slippage exceeded");
    // Execute swap...
}
```

---

### 6. Denial of Service (DoS)

**Risk**: An attacker makes a function permanently unusable by exploiting gas limits, unbounded loops, or unexpected reverts.

**Common patterns**:

- **Unbounded loops** over growing arrays — always paginate
- **Push-over-pull payments** — if one recipient reverts, all payments fail
- **Reliance on external calls** — a malicious contract can always revert

**Prevention — Pull over Push**:

```solidity
// BAD — push pattern (one revert blocks all)
function distributeRewards(address[] memory recipients) external {
    for (uint i = 0; i < recipients.length; i++) {
        payable(recipients[i]).transfer(reward); // If one reverts, all fail
    }
}

// GOOD — pull pattern (each user withdraws independently)
mapping(address => uint256) public rewards;

function claimReward() external {
    uint256 amount = rewards[msg.sender];
    require(amount > 0, "No reward");
    rewards[msg.sender] = 0;
    (bool success, ) = msg.sender.call{value: amount}("");
    require(success);
}
```

**Prevention — Bounded iterations**:

```solidity
// BAD — unbounded loop
function processAll() external {
    for (uint i = 0; i < users.length; i++) { ... }
}

// GOOD — paginated processing
function processBatch(uint256 start, uint256 count) external {
    uint256 end = start + count;
    if (end > users.length) end = users.length;
    for (uint256 i = start; i < end; i++) { ... }
}
```

---

### 7. Signature Replay

**Risk**: A valid signature is reused across transactions, chains, or contracts to perform unauthorized actions.

**Prevention**:

```solidity
// Include nonce and chain ID to prevent replay
mapping(address => uint256) public nonces;

function executeWithSignature(
    address signer,
    bytes calldata data,
    bytes calldata signature
) external {
    bytes32 hash = keccak256(abi.encodePacked(
        "\x19\x01",
        DOMAIN_SEPARATOR, // Includes chain ID and contract address
        keccak256(abi.encode(
            EXECUTE_TYPEHASH,
            signer,
            nonces[signer]++, // Incrementing nonce prevents replay
            keccak256(data)
        ))
    ));

    address recovered = ECDSA.recover(hash, signature);
    require(recovered == signer, "Invalid signature");
    // Execute action...
}
```

**Always include in signature messages**:
- Chain ID (prevents cross-chain replay)
- Contract address (prevents cross-contract replay)
- Nonce (prevents same-chain replay)
- Deadline (prevents stale signatures)

**Use EIP-712** for structured, human-readable signing. OpenZeppelin provides `EIP712` and `ECDSA` utilities.

---

### 8. Unsafe Delegatecall

**Risk**: `delegatecall` executes another contract's code in the context of the calling contract, meaning storage can be overwritten by the callee.

**Attack**: Attacker tricks a contract into delegatecalling to a malicious implementation that overwrites storage slot 0 (often the owner variable).

**Prevention**:

- Never `delegatecall` to user-supplied addresses
- In proxy patterns, ensure the implementation address is stored in an EIP-1967 slot and only updatable by authorized callers
- Use OpenZeppelin's proxy contracts (TransparentProxy, UUPS) which handle this safely

---

### 9. Uninitialized Proxy / Implementation

**Risk**: In upgradeable proxy patterns, failing to initialize the implementation contract allows an attacker to call `initialize()` and take ownership.

**Prevention**:

```solidity
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

contract MyContract is Initializable {
    address public owner;

    function initialize(address _owner) external initializer {
        owner = _owner;
    }
}
```

- Always use the `initializer` modifier on setup functions
- Call `_disableInitializers()` in implementation constructors to prevent direct initialization

---

## Radius-Specific Security Considerations

### Instant finality eliminates some risks

Radius's architecture removes several Ethereum-specific attack vectors:

| Attack Vector | Ethereum | Radius |
|--------------|----------|--------|
| **Reorg-based double-spend** | Possible (wait for confirmations) | Impossible (immediate finality) |
| **MEV / sandwich attacks** | Common (public mempool) | Minimal (no global mempool, per-shard consensus) |
| **Block-level manipulation** | Miners/validators can reorder | Raft consensus eliminates reordering |
| **Confirmation-based fraud** | Accept 1-confirmation, then reorg | Once confirmed, it is final |

### Stablecoin fee model considerations

- Gas price manipulation is not possible (fees are fixed at ~0.0001 USD)
- No gas token price volatility to exploit
- Failed transactions do not charge gas, so "griefing" via forced reverts has lower economic impact on users (but contracts should still guard against revert-based DoS)

### Native balance patterns

```solidity
// DON'T rely on native balance on Radius
require(address(this).balance > 0); // May not behave as expected

// DO use ERC-20 balance checks
require(IERC20(rusdToken).balanceOf(address(this)) > 0);
```

`eth_getBalance` on Radius returns native + convertible USD, which may differ from the contract's view of `address(this).balance`. Design payment flows around ERC-20 transfers.

### Still required on Radius

Despite the architectural improvements, all standard smart contract security practices still apply:

- Reentrancy protection
- Access control
- Input validation
- Safe math (default in 0.8+, careful with `unchecked`)
- Signature verification
- Proper event emission for off-chain indexing

---

## Program-Side Checklist

### Access Control
- [ ] All admin/privileged functions have explicit access modifiers (`onlyOwner`, `onlyRole`, etc.)
- [ ] Ownership transfer uses a two-step process (propose + accept) to prevent accidental lockout
- [ ] `initialize` functions use the `initializer` modifier and cannot be called twice
- [ ] Constructor sets initial access controls

### Input Validation
- [ ] All external function parameters are validated (non-zero addresses, bounds, array lengths)
- [ ] Reentrancy guard applied to functions that make external calls
- [ ] Deadlines and slippage parameters validated where applicable

### Token Safety
- [ ] Use `SafeERC20` for all token transfer operations
- [ ] Check return values of all low-level calls
- [ ] Verify token addresses are not zero
- [ ] Handle fee-on-transfer and rebasing tokens if your contract accepts arbitrary tokens
- [ ] Validate allowance before `transferFrom`

### Arithmetic
- [ ] Solidity 0.8+ is used (built-in overflow checks)
- [ ] `unchecked` blocks are only used where overflow is mathematically impossible
- [ ] Division-before-multiplication is avoided (precision loss)
- [ ] Casting between types is explicit and checked

### State Management
- [ ] Follow Checks-Effects-Interactions pattern
- [ ] No state changes after external calls (or behind reentrancy guard)
- [ ] Events emitted for all state changes (for off-chain indexing and monitoring)
- [ ] Emergency pause mechanism available via OpenZeppelin's `Pausable`
- [ ] Upgrade mechanism is properly access-controlled (if using proxies)

### External Interactions
- [ ] External contract addresses are validated before calls
- [ ] No `delegatecall` to user-supplied addresses
- [ ] CPI / cross-contract calls verify the target contract identity
- [ ] Interfaces match the actual deployed contract

---

## Client-Side Checklist

### Key Management
- [ ] Private keys stored in environment variables, never hardcoded
- [ ] `.env` files added to `.gitignore`
- [ ] Different keys used for development, testnet, and production
- [ ] Keys never logged, displayed, or transmitted
- [ ] Production keys managed via secrets manager or hardware wallet

### Transaction Safety
- [ ] Transactions are simulated before sending where feasible (`eth_call` / `eth_estimateGas`)
- [ ] Errors from failed simulations are surfaced to the user
- [ ] Transaction receipts are checked for `status === 'success'` before proceeding
- [ ] Amounts and recipients displayed to the user before signing
- [ ] Submit buttons are disabled after click to prevent duplicate submissions

### Network Safety
- [ ] Chain ID is validated before submitting transactions
- [ ] RPC endpoints are not hardcoded in client-side code if they contain API keys
- [ ] Testnet and mainnet configurations are separated
- [ ] Connection errors are handled gracefully with retry logic

### Payment Verification (Server-Side)
- [ ] Payment verification happens server-side, not client-side
- [ ] Transaction hashes are checked for replay (store processed hashes)
- [ ] Payment amounts and recipients are verified against expected values
- [ ] Transaction status is verified via receipt, not just hash existence
- [ ] Rate limiting is applied per wallet address

### User Experience
- [ ] Clear error messages for common failures (insufficient balance, wrong network, rejected signature)
- [ ] Loading states shown during wallet interaction and transaction confirmation
- [ ] Transaction hashes linked to block explorer for user verification
- [ ] Network addition prompt if user is on wrong chain

---

## Security Review Questions

Before deploying, ask yourself:

1. **Can an attacker call any function without proper authorization?** — Check all external/public functions for access controls.
2. **Can an attacker re-enter any function during an external call?** — Apply reentrancy guards and CEI pattern.
3. **Can an attacker manipulate function inputs to cause unexpected behavior?** — Validate all parameters.
4. **Can an attacker replay a valid signature?** — Include nonce, chain ID, contract address, and deadline.
5. **Can an attacker cause a function to revert permanently?** — Use pull patterns, bound loops, handle external call failures.
6. **Can an attacker exploit the contract through a malicious token or external contract?** — Validate external addresses, use SafeERC20.
7. **Can an attacker take ownership through initialization or upgrade?** — Protect initialize functions and upgrade mechanisms.
8. **Are all financial calculations correct?** — Check for precision loss, overflow in unchecked blocks, rounding errors.
9. **Are private keys and secrets properly managed?** — Environment variables, .gitignore, separate keys per environment.
10. **Is server-side verification in place for payment flows?** — Never trust client-side callbacks for payment confirmation.

---

## Recommended OpenZeppelin Contracts

| Contract | Purpose |
|----------|---------|
| `ReentrancyGuard` | Prevent reentrancy attacks |
| `Ownable` | Simple single-owner access control |
| `AccessControl` | Role-based access control |
| `Pausable` | Emergency stop mechanism |
| `SafeERC20` | Safe token transfer wrappers |
| `ECDSA` | Signature recovery and verification |
| `EIP712` | Structured data hashing for signatures |
| `Initializable` | Safe initialization for proxy patterns |
| `ERC20` / `ERC721` / `ERC1155` | Standard token implementations |

Install OpenZeppelin in your Foundry project:

```bash
forge install OpenZeppelin/openzeppelin-contracts
```
