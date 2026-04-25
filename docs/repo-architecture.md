# Repo Architecture

This repo needs to support two different layers without mixing them together:

1. Portable agent skills
2. Deterministic runtime adapters

## Source Of Truth

The source of truth for Radius skills lives under `skills/<skill>/`.

Each skill directory may contain:

- `SKILL.md`
- `references/`

These directories should stay portable. They should not depend on a specific agent runtime unless that dependency is clearly scoped and optional.

Behavior regression fixtures live separately under `spec/golden-tests/<skill>/`.

## Packaging Surfaces

Today the repo exposes a Claude-style adapter bundle at `adapters/claude-code` and marketplace metadata at `.claude-plugin/marketplace.json`.

Important compatibility rule:

- keep the existing bundle id `radius-dev` stable until there is an intentional migration path

That bundle now includes multiple Radius skills. The id is legacy; the contents are broader.

## Compatibility Model

| Framework | What works well here | Boundary |
| --- | --- | --- |
| Claude Code | Claude marketplace bundle plus portable skills | Current primary install surface |
| OpenClaw | Claude bundle compatibility for skills, settings, and MCP-backed features | A Hermes runtime module is not directly portable into OpenClaw bundle execution |
| Hermes | External skill roots plus native plugin adapters | Good fit for project-owned deterministic tool adapters |

## Deterministic Tool Rule

Skills describe how an agent should work. They should not be the only place where basic wallet logic lives.

For repetitive wallet operations like:

- wallet address lookup
- balance checks
- SBC transfers
- RUSD transfers
- transaction status checks

the repo should prefer deterministic runtime surfaces over prompt-generated scripts.

## Shared Runtime First

When the same deterministic capability needs to exist across more than one framework, the reusable core should be one of these:

- shared scripts with a stable CLI contract
- an MCP server with stable tool names and schemas

Framework adapters should stay thin and call the shared runtime instead of re-implementing business logic.

The current implementation lives at `runtimes/python/` so it can be consumed by both:

- Hermes-native adapters
- MCP loading via `adapters/claude-code/.mcp.json`

## Hermes Adapter Guidance

Hermes supports native project-owned plugins well. A Hermes adapter can legitimately provide:

- session-scoped wallet provider state
- thin tool wrappers
- Hermes-specific affordances around defaults and tool registration

The Hermes adapter should remain a wrapper layer over shared deterministic logic, not the only implementation.

The current Hermes adapter source lives at `adapters/hermes/radius-cast/`.
It resolves the shared runtime from:

- `RADIUS_RUNTIME_ROOT`
- `RADIUS_SKILLS_DIR/runtimes/python`
- `${HERMES_APP_ROOT}/vendor/radius-skills/runtimes/python`

## OpenClaw Adapter Guidance

OpenClaw can consume Claude bundles, but bundle support is selective. Skill content maps cleanly. Arbitrary Hermes-style runtime modules do not.

That means deterministic Radius tools for OpenClaw should take one of these forms:

- an OpenClaw native plugin
- bundle-provided MCP configuration that exposes a shared Radius MCP server

For cross-framework portability, MCP is the best common denominator when the same tool surface must work in both Hermes and OpenClaw.

This repo now includes that bundle-scoped MCP path. Per OpenClaw's documented bundle behavior, the MCP server key `radius` will expose provider-safe tool names prefixed as `radius__...` in OpenClaw.

## Wallet Provider Model

`local` and `para` wallet behavior belongs in the adapter layer, not the core skill layer.

Recommended split:

- shared runtime: provider-neutral wallet operations plus provider interfaces
- framework adapter: session defaults, provider switching, user-facing tool semantics

If Para credentials are available, adapters should steer users consistently and preserve a clear operator boundary around secret handling. The standalone Para reference remains:

- `https://github.com/getpara/para-wallet-skill`

## Near-Term Sequence

1. Normalize repo metadata and compatibility docs without breaking existing installs.
2. Extract a shared deterministic core for basic wallet operations.
3. Upstream a Hermes adapter that wraps the shared core instead of owning the logic.
4. Validate the OpenClaw MCP bundle path end to end and add a native plugin only if it buys something material.

## Contribution Rule

Before adding framework-specific runtime code, decide which layer it belongs to:

- skill content
- shared deterministic runtime
- Hermes adapter
- OpenClaw adapter

If the code cannot be shared, keep the framework-specific behavior small and explicit.
