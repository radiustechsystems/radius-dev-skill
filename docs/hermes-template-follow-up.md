# Hermes Template Follow-Up

Use this in the Hermes Railway template repo after the skills-repo PR below is open.

## Reference

- Skills PR: `[PASTE SKILLS PR URL HERE]`
- Preferred skills ref to consume: `[PASTE COMMIT SHA FROM THE SKILLS PR HERE]`

Prefer a pinned commit SHA from the skills PR over a moving branch name.

## Goal

Update the Hermes Railway template so it consumes the upstream Radius wallet plugin adapter and shared runtime from the Radius skills repo, instead of keeping a template-local `plugins/radius-cast` implementation.

The source of truth now lives in the skills repo:

- Hermes adapter: `adapters/hermes/radius-cast/`
- Shared deterministic runtime: `runtime/python/`
- MCP surface: `adapters/claude-code/.mcp.json`

## Desired Outcome

After this change:

- the Hermes template still exposes the `radius-cast` Hermes toolset
- the Hermes adapter is sourced from the vendored upstream Radius skills repo
- wallet logic is no longer duplicated in the Hermes template repo
- the shared runtime remains upstream in the Radius skills repo
- the template can temporarily pin to the skills PR commit until that PR merges

## Constraints

- Do not re-implement wallet logic in the Hermes template repo.
- Keep Hermes-specific session/provider behavior in the Hermes adapter only.
- Preserve existing Hermes behavior for:
  - session default provider = `local`
  - optional `para` provider
  - tool names:
    - `radius_wallet_address`
    - `radius_balance`
    - `radius_send_sbc`
    - `radius_send_rusd`
    - `radius_tx_status`
    - `radius_chain_info`
- Keep existing template-owned product behavior that does not belong upstream:
  - `skills/radius-wallet.md`
  - wallet bootstrap / first-boot init
  - A2A, JWT, discovery, ERC-8004, and template server code

## Required Changes

### 1. Vendor the upstream skills repo at the PR ref

Update the template build so the vendored Radius skills checkout can be pinned to the commit from the skills PR.

Recommended pattern:

- add a Docker build arg like `RADIUS_SKILLS_REF`
- clone `https://github.com/radiustechsystems/skills.git`
- check out the pinned commit SHA from the skills PR

Prefer a concrete commit SHA over a branch name.

### 2. Replace the template-local `radius-cast` plugin implementation

Stop using the template-local `plugins/radius-cast` code as the source of truth.

Instead, install the Hermes adapter from the vendored skills repo path:

- `/app/vendor/radius-skills/adapters/hermes/radius-cast`

That adapter is expected to resolve the shared runtime from:

- `RADIUS_RUNTIME_ROOT`
- `RADIUS_SKILLS_DIR/runtime/python`
- `${HERMES_APP_ROOT:-/app}/vendor/radius-skills/runtime/python`

Because the template already vendors upstream skills under `/app/vendor/radius-skills`, the adapter should work without extra glue if that path is preserved.

### 3. Keep the upstream runtime external

Do not copy the runtime logic into the template repo.

The shared runtime should remain upstream at:

- `/app/vendor/radius-skills/runtime/python`

If the install path changes, set `RADIUS_RUNTIME_ROOT` explicitly so the Hermes adapter can find it.

### 4. Preserve Hermes toolset enablement

Keep the existing `radius-cast` Hermes toolset enabled in config/bootstrap.

The toolset name should remain:

- `radius-cast`

The template should continue enabling it alongside the other bundled toolsets.

### 5. Update docs and operator notes

Update the Hermes template docs to reflect:

- `radius-cast` now comes from the upstream Radius skills repo
- deterministic wallet behavior lives in the upstream shared runtime
- the template still owns wallet bootstrap and user-facing `radius-wallet` skill behavior

### 6. Remove duplicated local implementation

Delete or stop wiring the old template-local `plugins/radius-cast` implementation once the upstream adapter is installed.

Do not leave two competing implementations active.

## Suggested File Targets

Adjust as needed for the current template repo layout, but expect to touch:

- `Dockerfile`
- `scripts/entrypoint.sh`
- `README.md`
- `HERMES.md`
- `AGENTS.md`
- any template-local `plugins/radius-cast/*` files

## Validation

Verify all of the following:

1. The vendored skills repo is pinned to the requested PR commit.
2. Hermes loads the upstream `radius-cast` adapter successfully.
3. The adapter resolves the shared runtime without local path hacks.
4. The following tools are registered and callable:
   - `radius_wallet_address`
   - `radius_balance`
   - `radius_send_sbc`
   - `radius_send_rusd`
   - `radius_tx_status`
   - `radius_chain_info`
5. Provider switching still behaves correctly:
   - default `local`
   - explicit `para`
   - hard error if `para` is requested but unavailable
6. Existing non-wallet template behavior is unchanged.

## Acceptance Criteria

- No duplicated `radius-cast` wallet logic remains in the Hermes template repo.
- Hermes-specific wrapper behavior remains in the adapter layer only.
- Shared deterministic wallet logic is sourced from the Radius skills repo.
- The template can be tested against the skills PR commit before the skills PR merges.

## Notes

- This work depends on the skills PR listed above.
- If there is any ambiguity between copying files and resolving them from the vendored upstream source, prefer resolving from the vendored upstream source.
- If a temporary compatibility shim is needed, keep it small and delete it once the upstream path is stable.
