#!/usr/bin/env python3
"""
Validate and publish Radius skills webhook updates to subscribed Hermes agents.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HTTPS_URL_RE = re.compile(r"^https://[^\s]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


@dataclass
class Subscriber:
    id: str
    enabled: bool
    name: str
    webhook_url: str
    secret_key: str
    branch: str | None = None
    repo_full_name: str | None = None


def _is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_manifest(path: Path) -> tuple[dict[str, Any], list[Subscriber]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Manifest is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise SystemExit("Manifest root must be a JSON object")

    subscribers_raw = raw.get("subscribers")
    if not isinstance(subscribers_raw, list):
        raise SystemExit("Manifest must contain a 'subscribers' array")

    subscribers: list[Subscriber] = []
    for item in subscribers_raw:
        if not isinstance(item, dict):
            raise SystemExit("Each subscriber entry must be a JSON object")
        subscribers.append(
            Subscriber(
                id=str(item.get("id") or "").strip(),
                enabled=bool(item.get("enabled", True)),
                name=str(item.get("name") or "").strip(),
                webhook_url=str(item.get("webhook_url") or "").strip(),
                secret_key=str(item.get("secret_key") or "").strip(),
                branch=str(item.get("branch") or "").strip() or None,
                repo_full_name=str(item.get("repo_full_name") or "").strip() or None,
            )
        )
    return raw, subscribers


def validate_manifest(path: Path) -> int:
    raw, subscribers = _load_manifest(path)
    errors: list[str] = []
    seen_ids: set[str] = set()

    version = raw.get("version")
    if version != 1:
        errors.append("Manifest 'version' must be 1")

    for idx, sub in enumerate(subscribers):
        label = f"subscribers[{idx}]"
        if not sub.id:
            errors.append(f"{label}.id is required")
        elif sub.id in seen_ids:
            errors.append(f"{label}.id '{sub.id}' is duplicated")
        else:
            seen_ids.add(sub.id)

        if not sub.name:
            errors.append(f"{label}.name is required")
        if not sub.secret_key:
            errors.append(f"{label}.secret_key is required")
        if not sub.webhook_url:
            errors.append(f"{label}.webhook_url is required")
        elif not HTTPS_URL_RE.match(sub.webhook_url):
            errors.append(f"{label}.webhook_url must be https")

        if sub.branch and not BRANCH_RE.match(sub.branch):
            errors.append(f"{label}.branch contains invalid characters")

        if sub.repo_full_name:
            parts = sub.repo_full_name.split("/")
            if len(parts) != 2 or not all(parts):
                errors.append(f"{label}.repo_full_name must look like owner/repo")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(subscribers)} subscriber entries in {path}")
    return 0


def _github_event() -> dict[str, Any]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise SystemExit("GITHUB_EVENT_PATH is required")
    try:
        return json.loads(Path(event_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Failed to read GitHub event payload: {exc}") from exc


def _manual_inputs() -> dict[str, Any]:
    after = os.environ.get("RADIUS_MANUAL_AFTER", "").strip()
    before = os.environ.get("RADIUS_MANUAL_BEFORE", "").strip()
    branch = os.environ.get("RADIUS_MANUAL_BRANCH", "").strip()
    repo_full_name = os.environ.get("RADIUS_MANUAL_REPOSITORY", "").strip()
    subscriber_id = os.environ.get("RADIUS_MANUAL_SUBSCRIBER_ID", "").strip()

    if not after:
        raise SystemExit("RADIUS_MANUAL_AFTER is required for workflow_dispatch runs")
    if not HEX_SHA_RE.match(after):
        raise SystemExit("RADIUS_MANUAL_AFTER must be a git sha")
    if before and not HEX_SHA_RE.match(before):
        raise SystemExit("RADIUS_MANUAL_BEFORE must be a git sha when provided")
    if branch and not BRANCH_RE.match(branch):
        raise SystemExit("RADIUS_MANUAL_BRANCH contains invalid characters")
    if repo_full_name:
        parts = repo_full_name.split("/")
        if len(parts) != 2 or not all(parts):
            raise SystemExit("RADIUS_MANUAL_REPOSITORY must look like owner/repo")

    return {
        "after": after,
        "before": before or "0000000000000000000000000000000000000000",
        "branch": branch or os.environ.get("GITHUB_REF_NAME", "main"),
        "repository": repo_full_name or os.environ.get("GITHUB_REPOSITORY", ""),
        "subscriber_id": subscriber_id or None,
    }


def _build_payloads() -> tuple[dict[str, Any], str | None]:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    if event_name == "workflow_dispatch":
        manual = _manual_inputs()
        payload = {
            "ref": f"refs/heads/{manual['branch']}",
            "before": manual["before"],
            "after": manual["after"],
            "repository": {"full_name": manual["repository"]},
            "head_commit": {"id": manual["after"]},
            "commits": [],
            "pusher": {"name": "github-actions[bot]"},
            "sender": {"login": "github-actions[bot]"},
            "workflow_dispatch": True,
        }
        return payload, manual["subscriber_id"]

    event = _github_event()
    payload = {
        "ref": event.get("ref"),
        "before": event.get("before"),
        "after": event.get("after"),
        "repository": {
            "full_name": ((event.get("repository") or {}).get("full_name")) or os.environ.get("GITHUB_REPOSITORY", "")
        },
        "head_commit": event.get("head_commit"),
        "commits": event.get("commits") or [],
        "pusher": event.get("pusher"),
        "sender": event.get("sender"),
    }
    return payload, None


def _subscriber_secret_map() -> dict[str, str]:
    raw = os.environ.get("RADIUS_SUBSCRIBER_WEBHOOK_SECRETS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"RADIUS_SUBSCRIBER_WEBHOOK_SECRETS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("RADIUS_SUBSCRIBER_WEBHOOK_SECRETS_JSON must be a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


def _masked_secret(secret_key: str) -> str:
    digest = hashlib.sha256(secret_key.encode("utf-8")).hexdigest()
    return digest[:12]


def _delivery_id() -> str:
    return str(uuid.uuid4())


def _send_webhook(
    subscriber: Subscriber,
    payload: dict[str, Any],
    secret: str,
    timeout_seconds: int,
    dry_run: bool,
    warning: str | None = None,
) -> dict[str, Any]:
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    delivery_id = _delivery_id()

    if dry_run:
        return {
            "subscriber_id": subscriber.id,
            "name": subscriber.name,
            "status": "dry_run",
            "code": None,
            "delivery_id": delivery_id,
            "target": subscriber.webhook_url,
            "secret_ref": _masked_secret(subscriber.secret_key),
            "payload_after": payload.get("after"),
            "warning": warning,
        }

    req = urllib.request.Request(
        subscriber.webhook_url,
        data=raw_payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "radius-skills-publisher/1.0",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": signature,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read(2048).decode("utf-8", errors="replace")
            return {
                "subscriber_id": subscriber.id,
                "name": subscriber.name,
                "status": "ok",
                "code": getattr(resp, "status", 200),
                "delivery_id": delivery_id,
                "target": subscriber.webhook_url,
                "response": body,
                "payload_after": payload.get("after"),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", errors="replace")
        return {
            "subscriber_id": subscriber.id,
            "name": subscriber.name,
            "status": "error",
            "code": exc.code,
            "delivery_id": delivery_id,
            "target": subscriber.webhook_url,
            "response": body,
            "error": f"HTTP {exc.code}",
            "payload_after": payload.get("after"),
        }
    except Exception as exc:
        return {
            "subscriber_id": subscriber.id,
            "name": subscriber.name,
            "status": "error",
            "code": None,
            "delivery_id": delivery_id,
            "target": subscriber.webhook_url,
            "error": str(exc),
            "payload_after": payload.get("after"),
        }


def _write_summary(summary_path: str | None, payload: dict[str, Any], results: list[dict[str, Any]]) -> None:
    if not summary_path:
        return
    lines = [
        "# Radius Skills Webhook Publish",
        "",
        f"- Ref: `{payload.get('ref')}`",
        f"- Before: `{payload.get('before')}`",
        f"- After: `{payload.get('after')}`",
        f"- Repository: `{((payload.get('repository') or {}).get('full_name')) or ''}`",
        "",
        "| Subscriber | Status | Code | Delivery |",
        "| --- | --- | --- | --- |",
    ]

    for result in results:
        lines.append(
            f"| `{result['subscriber_id']}` | `{result['status']}` | `{result.get('code') or ''}` | `{result['delivery_id']}` |"
        )
        if result.get("error"):
            lines.append("")
            lines.append(f"- `{result['subscriber_id']}` error: {result['error']}")
        elif result.get("warning"):
            lines.append("")
            lines.append(f"- `{result['subscriber_id']}` warning: {result['warning']}")
        elif result.get("response") and result["status"] != "ok":
            lines.append("")
            lines.append(f"- `{result['subscriber_id']}` response: `{result['response'][:200]}`")

    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish(manifest_path: Path) -> int:
    _, subscribers = _load_manifest(manifest_path)
    payload, targeted_subscriber = _build_payloads()
    secrets = _subscriber_secret_map()
    timeout_seconds = int(os.environ.get("RADIUS_PUBLISH_TIMEOUT_SECONDS", "20"))
    dry_run = _is_true(os.environ.get("RADIUS_DRY_RUN"))
    ignore_failures = _is_true(os.environ.get("RADIUS_IGNORE_FAILURES"))
    branch = str(payload.get("ref") or "").replace("refs/heads/", "", 1)

    if not payload.get("after"):
        raise SystemExit("No payload 'after' sha was resolved")

    eligible = []
    for subscriber in subscribers:
        if not subscriber.enabled:
            continue
        if targeted_subscriber and subscriber.id != targeted_subscriber:
            continue
        if subscriber.branch and subscriber.branch != branch:
            continue
        eligible.append(subscriber)

    if targeted_subscriber and not any(sub.id == targeted_subscriber for sub in eligible):
        raise SystemExit(f"Target subscriber '{targeted_subscriber}' was not found or is not enabled for branch '{branch}'")

    print(f"Publishing skills update to {len(eligible)} subscriber(s) for {payload['after']}")

    results: list[dict[str, Any]] = []
    for subscriber in eligible:
        payload_for_subscriber = json.loads(json.dumps(payload))
        if subscriber.repo_full_name:
            payload_for_subscriber["repository"]["full_name"] = subscriber.repo_full_name

        secret = secrets.get(subscriber.secret_key, "")
        if not secret:
            if dry_run:
                results.append(
                    _send_webhook(
                        subscriber,
                        payload_for_subscriber,
                        "dry-run-placeholder-secret",
                        timeout_seconds,
                        dry_run=True,
                        warning=f"Missing secret for key '{subscriber.secret_key}'",
                    )
                )
                continue
            results.append(
                {
                    "subscriber_id": subscriber.id,
                    "name": subscriber.name,
                    "status": "error",
                    "code": None,
                    "delivery_id": _delivery_id(),
                    "target": subscriber.webhook_url,
                    "error": f"Missing secret for key '{subscriber.secret_key}'",
                    "payload_after": payload_for_subscriber.get("after"),
                }
            )
            continue

        result = _send_webhook(subscriber, payload_for_subscriber, secret, timeout_seconds, dry_run)
        results.append(result)
        print(
            f"[{result['status']}] {subscriber.id} "
            f"code={result.get('code') or '-'} delivery={result['delivery_id']}"
        )

    _write_summary(os.environ.get("GITHUB_STEP_SUMMARY"), payload, results)

    failures = [result for result in results if result["status"] == "error"]
    if failures and not ignore_failures:
        for failure in failures:
            print(
                f"FAILED subscriber={failure['subscriber_id']} "
                f"target={failure['target']} "
                f"error={failure.get('error') or failure.get('response') or 'unknown'}",
                file=sys.stderr,
            )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "publish"])
    parser.add_argument("--manifest", default=".github/radius-subscribers.json")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if args.command == "validate":
        return validate_manifest(manifest_path)
    if args.command == "publish":
        return publish(manifest_path)
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
