#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = ["radius-dev", "x402", "dripping-faucet", "radius-agent-ops"]
EXPECTED_TOOLS = [
    "radius_wallet_address",
    "radius_balance",
    "radius_send_sbc",
    "radius_send_rusd",
    "radius_tx_status",
    "radius_chain_info",
]


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env, text=True, capture_output=True)
    if result.returncode != 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes install smoke test for Radius skills + tools")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Radius skills repo root")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    with tempfile.TemporaryDirectory(prefix="radius-hermes-install-") as tmp:
        tmp_path = Path(tmp)
        hermes_home = tmp_path / ".hermes"
        skills_dir = tmp_path / "external-skills" / "radius-skills"
        plugin_dir = hermes_home / "plugins" / "radius-cast"
        runtime_dir = skills_dir / "runtimes" / "python"
        shutil.copytree(repo_root, skills_dir, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        shutil.copytree(skills_dir / "adapters" / "hermes" / "radius-cast", plugin_dir)
        env = os.environ.copy()
        env.update(
            {
                "HERMES_HOME": str(hermes_home),
                "RADIUS_SKILLS_DIR": str(skills_dir),
                "RADIUS_RUNTIME_ROOT": str(runtime_dir),
            }
        )
        probe = r'''
import importlib.util, json, os, sys
from pathlib import Path
class Ctx:
    def __init__(self):
        self.tools=[]
        self.hooks=[]
    def register_tool(self, **kwargs):
        self.tools.append(kwargs)
    def register_hook(self, name, callback):
        self.hooks.append((name, callback))
plugin = Path(os.environ["HERMES_HOME"]) / "plugins" / "radius-cast" / "__init__.py"
spec = importlib.util.spec_from_file_location("radius_cast_smoke", plugin)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ctx = Ctx()
mod.register(ctx)
print(json.dumps({
  "tools": sorted(tool["name"] for tool in ctx.tools),
  "hooks": sorted(name for name, _ in ctx.hooks),
}))
'''
        output = run([sys.executable, "-c", probe], env=env)
        payload = json.loads(output)
        missing_tools = sorted(set(EXPECTED_TOOLS) - set(payload["tools"]))
        if missing_tools:
            raise SystemExit(f"missing Hermes tools after install: {missing_tools}")
        for skill_name in EXPECTED_SKILLS:
            if not (skills_dir / "skills" / skill_name / "SKILL.md").exists():
                raise SystemExit(f"missing portable skill: {skill_name}")
        if not (runtime_dir / "radius_wallet_runtime.py").exists():
            raise SystemExit("missing shared Radius wallet runtime")
        print(json.dumps({"ok": True, "tools": payload["tools"], "skills": EXPECTED_SKILLS}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
