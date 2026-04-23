# Radius Skills Marketplace

Radius-maintained agent skills for building on the Radius Network.

This repo currently serves two purposes:

- the upstream source of truth for portable Radius skills
- the install surface for the existing Claude-style `radius-dev` bundle

The current marketplace bundle id stays `radius-dev` for backward compatibility, but the bundle now spans multiple skills including `radius-dev`, `dripping-faucet`, and `radius-agent-ops`.

## Repo Layout

- `plugins/radius/skills/*` — source of truth for Radius skills
- `plugins/radius/runtime/*` — shared deterministic Radius wallet runtime, CLI, and MCP server
- `plugins/radius/.claude-plugin/plugin.json` — Claude bundle manifest used by the current marketplace package
- `plugins/radius/.mcp.json` — bundle-scoped MCP config for OpenClaw-compatible loading
- `.claude-plugin/marketplace.json` — marketplace root metadata
- `docs/repo-architecture.md` — compatibility boundaries and adapter design rules

## Compatibility

| Surface | Status | Notes |
| --- | --- | --- |
| Claude Code bundle | Supported | Current install path. The legacy bundle id `radius-dev` remains stable for existing users. |
| OpenClaw bundle | Supported for skills, experimental for deterministic tools | OpenClaw can ingest Claude bundles and map skill content from them. This repo now ships a bundle-scoped MCP runtime for Radius wallet tools, but that path still needs end-to-end framework verification. |
| Hermes external skills | Supported downstream | Hermes templates can consume this repo as external skill roots today. |
| Hermes native tool adapter | Supported upstream | Source now lives in `adapters/hermes/radius-cast` and wraps the shared runtime instead of owning wallet logic. |
| Other frameworks | Untested | Document the pattern, but do not claim support until verified. |

## Installation

### Claude Code

```bash
/plugin marketplace add https://github.com/radiustechsystems/skills.git
/plugin install radius@radius-dev-skill
```

### OpenClaw

Install the existing Claude bundle directly from this repo:

```bash
openclaw plugins install radius-dev --marketplace https://github.com/radiustechsystems/skills
openclaw gateway restart
```

For local development from a checkout:

```bash
openclaw plugins install ./plugins/radius
openclaw gateway restart
```

### npx skills

```bash
npx skills add radiustechsystems/skills
```

## Design Rule

Skills should tell an agent how to operate, but basic wallet operations should not force the model to rewrite the same code every turn.

The direction for deterministic Radius tooling in this repo is:

- keep skills portable and framework-agnostic
- put deterministic logic behind shared runtime surfaces
- add thin framework adapters on top of that shared runtime

For the current architecture and adapter guidance, see [docs/repo-architecture.md](docs/repo-architecture.md).

## Deterministic Runtime

The shared Radius wallet runtime now lives under `plugins/radius/runtime/`.

It currently provides:

- a Python runtime API for deterministic wallet operations
- a stable JSON CLI
- a stdio MCP server exposed from `plugins/radius/.mcp.json`

The current tool surface is:

- `radius_wallet_address`
- `radius_balance`
- `radius_send_sbc`
- `radius_send_rusd`
- `radius_tx_status`
- `radius_chain_info`

Runtime expectations:

- local provider flows require Foundry `cast`
- Para flows additionally require `requests` and `web3`
- wallet state defaults to `RADIUS_STATE_DIR`, then `HERMES_HOME/.radius`, then `~/.radius`

## Hermes Adapter

The upstream Hermes adapter now lives at `adapters/hermes/radius-cast/`.

It resolves the shared runtime in this order:

- `RADIUS_RUNTIME_ROOT`
- `RADIUS_SKILLS_DIR/plugins/radius/runtime`
- `${HERMES_APP_ROOT:-/app}/vendor/radius-skills/plugins/radius/runtime`

That keeps Hermes-specific session/provider behavior in the adapter while leaving the actual wallet logic in the shared runtime.
