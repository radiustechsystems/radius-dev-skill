# Curated Resources

## Radius Documentation & Tools

- [Radius Documentation](https://docs.radiustech.xyz/) — Official developer documentation
- [Ethereum compatibility](https://docs.radiustech.xyz/developer-resources/ethereum-compatibility.md) — EVM behavior differences, Turnstile, balance methods, RPC constraints
- [Tooling configuration](https://docs.radiustech.xyz/developer-resources/tooling-configuration.md) — Foundry, viem, wagmi, Hardhat, ethers.js setup
- [Fees](https://docs.radiustech.xyz/developer-resources/fees.md) — Fee structure and transaction costs
- [JSON-RPC API reference](https://docs.radiustech.xyz/developer-resources/json-rpc-api.md) — Method support, EIP-7966, error codes
- [Radius Network Explorer (mainnet)](https://network.radiustech.xyz) — Block explorer for Radius Network
- [Radius Testnet Explorer](https://testnet.radiustech.xyz) — Block explorer for Radius Testnet
- [Radius Discord](https://discord.gg/radiustech) — Community support and discussions

### LLM-friendly documentation

- [`/llms.txt`](https://docs.radiustech.xyz/llms.txt) — Compact index of key docs (for LLM context windows)
- [`/llms-full.txt`](https://docs.radiustech.xyz/llms-full.txt) — Full corpus for broader ingestion
- Append `.md` to any docs URL for plain-text Markdown format

## Radius Tools

- [Radius Dev Skill for Claude Code](https://github.com/radiustechsystems/skills) — Claude Code plugin / skills.sh skill

## EVM Development (Core Libraries)

### viem
- [viem Documentation](https://viem.sh/) — TypeScript interface for Ethereum
- [viem GitHub](https://github.com/wevm/viem)
- [viem Actions](https://viem.sh/docs/actions/public/introduction) — Public, wallet, and test actions

### wagmi
- [wagmi Documentation](https://wagmi.sh/) — React hooks for Ethereum
- [wagmi GitHub](https://github.com/wevm/wagmi)
- [wagmi React Hooks Reference](https://wagmi.sh/react/api/hooks) — useAccount, useConnect, useSendTransaction, etc.

### @tanstack/react-query
- [TanStack Query Documentation](https://tanstack.com/query) — Required peer dependency for wagmi

### Hardhat
- [Hardhat Documentation](https://hardhat.org/) — Pin to v2 for Radius compatibility (`hardhat@^2.22.0`; v3 incompatible)

### ethers.js
- [ethers.js Documentation](https://docs.ethers.org/) — Works out of the box with Radius (no overrides needed)

## Smart Contract Development

### Foundry
- [Foundry Book](https://book.getfoundry.sh/) — Complete Foundry documentation
- [Foundry GitHub](https://github.com/foundry-rs/foundry)
- [forge create](https://book.getfoundry.sh/reference/forge/forge-create) — Deploy contracts
- [forge script](https://book.getfoundry.sh/reference/forge/forge-script) — Scripted deployments
- [forge test](https://book.getfoundry.sh/reference/forge/forge-test) — Testing framework
- [cast](https://book.getfoundry.sh/reference/cast/cast) — CLI for contract interaction

### OpenZeppelin
- [OpenZeppelin Contracts](https://docs.openzeppelin.com/contracts/) — Standard contract library
- [OpenZeppelin GitHub](https://github.com/OpenZeppelin/openzeppelin-contracts)
- [OpenZeppelin Wizard](https://wizard.openzeppelin.com/) — Generate contract boilerplate
- Key contracts for Radius development:
  - `ERC20` — Standard token implementation
  - `SafeERC20` — Safe transfer wrappers (critical for Radius payment patterns)
  - `Ownable` / `AccessControl` — Access control
  - `ReentrancyGuard` — Reentrancy protection
  - `Pausable` — Emergency stop mechanism
  - `EIP712` / `ECDSA` — Signature utilities

### Solidity
- [Solidity Documentation](https://docs.soliditylang.org/) — Language reference
- [Solidity by Example](https://solidity-by-example.org/) — Practical code examples
- [EVM Codes](https://www.evm.codes/) — Opcode reference and gas costs

## Standards & EIPs

- [ERC-20](https://eips.ethereum.org/EIPS/eip-20) — Fungible token standard
- [ERC-721](https://eips.ethereum.org/EIPS/eip-721) — Non-fungible token standard
- [ERC-1155](https://eips.ethereum.org/EIPS/eip-1155) — Multi-token standard
- [EIP-712](https://eips.ethereum.org/EIPS/eip-712) — Typed structured data hashing and signing
- [EIP-1193](https://eips.ethereum.org/EIPS/eip-1193) — Ethereum provider JavaScript API (wallet standard)
- [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559) — Fee market (adapted for stablecoins on Radius)
- [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930) — Access lists
- [EIP-4844](https://eips.ethereum.org/EIPS/eip-4844) — Blob transactions
- [EIP-7702](https://eips.ethereum.org/EIPS/eip-7702) — Set EOA account code
- [EIP-7966](https://eips.ethereum.org/EIPS/eip-7966) — `eth_sendRawTransactionSync` (synchronous tx submission; supported on Radius)

## Wallet Integration

- [MetaMask Documentation](https://docs.metamask.io/) — Browser wallet
- [WalletConnect](https://docs.walletconnect.com/) — Multi-wallet protocol
- [Rainbow Kit](https://www.rainbowkit.com/) — React wallet connection UI
- [ConnectKit](https://docs.family.co/connectkit) — Alternative wallet connection UI

## x402 Protocol

- [x402.org](https://www.x402.org/) — Protocol specification and overview
- [Radius x402 Integration (live docs)](https://docs.radiustech.xyz/developer-resources/x402-integration.md) — Radius-native x402 integration guide (always current)
- [Stablecoin.xyz x402 overview](https://docs.stablecoin.xyz/x402/overview) — Hosted facilitator tooling for Radius
- [Stablecoin.xyz x402 client docs](https://docs.stablecoin.xyz/x402/sdk) — Client documentation
- [Stablecoin.xyz x402 facilitator](https://docs.stablecoin.xyz/x402/facilitator) — Facilitator documentation

### Endorsed facilitators
- Stablecoin.xyz: `https://x402.stablecoin.xyz` (mainnet + testnet, v1 + v2)
- FareSide: `https://facilitator.x402.rs` (testnet only, v2)
- Middlebit: `https://middlebit.com` (mainnet, routes via stablecoin.xyz)

## Deployed Contracts

### Radius Network (mainnet)

| Contract | Address | Decimals |
|----------|---------|----------|
| SBC Token | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | **6** |
| Arachnid Create2 Factory | `0x4e59b44847b379578588920cA78FbF26c0B4956C` | — |
| Permit2 | `0x000000000022D473030F116dDEE9F6B43aC78BA3` | — |
| Multicall3 | `0xcA11bde05977b3631167028862bE2a173976CA11` | — |
| CreateX | `0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed` | — |

### Radius Testnet

| Contract | Address | Decimals |
|----------|---------|----------|
| SBC Token | `0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb` | **6** |
| Arachnid Create2 Factory | `0x4e59b44847b379578588920cA78FbF26c0B4956C` | — |
| CreateX | `0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed` | — |
| Multicall3 | `0xcA11bde05977b3631167028862bE2a173976CA11` | — |
| Permit2 | `0x000000000022D473030F116dDEE9F6B43aC78BA3` | — |
| EntryPoint v0.7 | `0x9b443e4bd122444852B52331f851a000164Cc83F` | — |
| SimpleAccountFactory | `0x4DEbDe0Be05E51432D9afAf61D84F7F0fEA63495` | — |

## Bridging

Bridge stablecoins (USDC, SBC) to Radius from other networks:

| Source | Estimated time | Notes |
|--------|---------------|-------|
| Ethereum → Radius | ~5-10 minutes | USDC and SBC supported |
| Base → Radius | ~1-2 minutes | USDC and SBC supported |

See the [Getting Started guide](https://docs.radiustech.xyz/get-started/getting-started.md) for bridge URLs and step-by-step instructions.

## Security Resources

- [OpenZeppelin Security Audits](https://www.openzeppelin.com/security-audits) — Industry-standard auditing
- [Slither](https://github.com/crytic/slither) — Static analysis framework for Solidity
- [Mythril](https://github.com/Consensys/mythril) — Security analysis tool
- [Aderyn](https://github.com/Cyfrin/aderyn) — Rust-based Solidity static analyzer
- [Solidity Security Best Practices](https://consensys.github.io/smart-contract-best-practices/) — ConsenSys guide
- [SWC Registry](https://swcregistry.io/) — Smart contract weakness classification

## Architecture References

- [PArSEC Paper](https://dci.mit.edu/s/p.pdf) — Parallel Sharded Transactions with Contracts (Radius's theoretical foundation)
- [Raft Consensus](https://raft.github.io/) — Consensus algorithm used per-shard in Radius
