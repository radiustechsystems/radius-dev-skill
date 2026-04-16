# Radius Skills Marketplace

A Claude Code plugin marketplace from Radius providing skills to enhance AI-assisted development workflows.

## Installation

### Claude Code

```bash
/plugin marketplace add https://github.com/radiustechsystems/skills.git

/plugin install radius@radius-dev-skill
```

### npx skills

```bash
npx skills add radiustechsystems/skills
```

## Hermes Subscriber Publishing

This repo can publish a GitHub `push`-shaped webhook to Hermes agents that were deployed from the Radius Hermes Railway Template with webhook-based skills sync enabled.

The publisher lives in:

- `.github/workflows/publish-radius-skills-update.yml`
- `.github/radius-subscribers.json`
- `scripts/radius_subscribers.py`

The subscriber manifest already includes a disabled ready-to-edit template entry so new agents can be added by copying or editing an existing shape instead of starting from scratch.

### What gets sent

Each subscriber receives:

- `POST <subscriber.webhook_url>`
- `X-GitHub-Event: push`
- `X-GitHub-Delivery: <uuid>`
- `X-Hub-Signature-256: sha256=<hmac>`

The body is a minimal GitHub push payload containing:

- `repository.full_name`
- `ref`
- `before`
- `after`
- `head_commit`
- `commits`

This matches the webhook contract expected by the Hermes runtime sync endpoint added in the Railway Template PR.

Important repo slug note:

- this repo currently publishes from `radiustechsystems/radius-dev-skill`
- Hermes subscribers should ideally set `RADIUS_SKILLS_REPO=radiustechsystems/radius-dev-skill`
- if a subscriber still expects the legacy `radiustechsystems/skills` slug, set `repo_full_name` on that manifest entry as a temporary compatibility override

### Automatic publishing

The workflow publishes automatically on pushes to any branch.

Actual delivery is still branch-aware:

- a subscriber only receives updates when its manifest `branch` matches the pushed branch
- this lets you wire a staging or PR-test Hermes agent to a feature branch without notifying production agents on that branch

Typical setup:

- production agent entry: `branch: "main"`
- test agent entry: `branch: "feature/my-skill-pr"` or another dedicated preview branch

When you push new commits to that PR branch, the workflow publishes the corresponding webhook to subscribers for that branch.

### Manual replay

Use the `Publish Radius Skills Update` workflow with `workflow_dispatch` to replay a specific commit, optionally for a single subscriber.

Recommended manual inputs:

- `after`: target commit SHA
- `before`: previous commit SHA if you want an accurate replay payload
- `subscriber_id`: optional targeted replay
- `dry_run`: validate without sending

### Subscriber registry

Subscriber routing is stored in `.github/radius-subscribers.json`.

Example:

```json
{
  "version": 1,
  "subscribers": [
    {
      "id": "example-hermes-agent",
      "enabled": false,
      "name": "Example Hermes Agent",
      "webhook_url": "https://your-agent.example.com/webhooks/github/radius-skills",
      "secret_key": "example_hermes_agent",
      "branch": "main",
      "repo_full_name": "radiustechsystems/radius-dev-skill"
    }
  ]
}
```

Recommended workflow:

1. Copy the disabled example entry.
2. Replace the `id`, `name`, `webhook_url`, and `secret_key`.
3. Set `branch` to the branch that agent should follow.
4. Leave `repo_full_name` as `radiustechsystems/radius-dev-skill` unless you intentionally need a compatibility override.
5. Set `enabled` to `true` only when the Hermes deployment and shared secret are ready.

Fields:

- `id`: stable operator-facing identifier used for targeted replay
- `enabled`: set `false` to disable delivery without deleting history
- `name`: descriptive label for workflow summaries
- `webhook_url`: full Hermes webhook endpoint
- `secret_key`: key used to look up the shared secret in the GitHub secret map
- `branch`: optional branch filter, usually `main`
- `repo_full_name`: optional payload override if a subscriber expects a specific `owner/repo`

### Secrets

Webhook secrets are provided through one GitHub Actions secret:

- `RADIUS_SUBSCRIBER_WEBHOOK_SECRETS_JSON`

Example value:

```json
{
  "example_hermes_agent": "replace-with-the-shared-webhook-secret",
  "agent_prod_1": "super-secret-value",
  "agent_staging": "another-secret"
}
```

The manifest stays in git. Shared secrets stay in GitHub secrets.

### Adding a subscriber

1. Add a new entry to `.github/radius-subscribers.json`.
2. Add the matching key/value to `RADIUS_SUBSCRIBER_WEBHOOK_SECRETS_JSON`.
3. Ensure the Hermes agent is configured with:
   - `RADIUS_SKILLS_AUTO_UPDATE=true`
   - matching `RADIUS_SKILLS_WEBHOOK_SECRET`
   - the expected `RADIUS_SKILLS_REPO` and `RADIUS_SKILLS_BRANCH`
4. Merge to `main` or run the manual publish workflow.

Fastest path:

1. Edit the disabled `example-hermes-agent` entry in `.github/radius-subscribers.json`.
2. Add the real shared secret under the same `secret_key` in `RADIUS_SUBSCRIBER_WEBHOOK_SECRETS_JSON`.
3. Flip `enabled` to `true`.

### Testing a skill PR on an agent before merge

To test a PR branch against a Hermes agent:

1. Configure the target Hermes agent with:
   - `RADIUS_SKILLS_AUTO_UPDATE=true`
   - matching `RADIUS_SKILLS_WEBHOOK_SECRET`
   - `RADIUS_SKILLS_BRANCH=<your-pr-branch>`
   - `RADIUS_SKILLS_REPO=radiustechsystems/radius-dev-skill`
2. Add or update a subscriber entry in `.github/radius-subscribers.json` with that same `branch`.
3. Push commits to the PR branch.

The publish workflow will run on that branch push and notify only the subscribers configured for that branch.

For one-off tests, you can also use `workflow_dispatch` and set:

- `branch` to the PR branch
- `subscriber_id` to the test agent
- `after` to the commit you want Hermes to sync

Suggested test entry:

```json
{
  "id": "my-skill-pr-agent",
  "enabled": true,
  "name": "Skill PR Test Agent",
  "webhook_url": "https://my-test-agent.example.com/webhooks/github/radius-skills",
  "secret_key": "my_skill_pr_agent",
  "branch": "feature/my-skill-pr",
  "repo_full_name": "radiustechsystems/radius-dev-skill"
}
```

### Removing a subscriber

1. Set `enabled` to `false` or remove the manifest entry.
2. Remove the unused secret from `RADIUS_SUBSCRIBER_WEBHOOK_SECRETS_JSON`.

### Validation

The subscriber manifest is validated by GitHub Actions and can also be checked locally:

```bash
python3 scripts/radius_subscribers.py validate
```
