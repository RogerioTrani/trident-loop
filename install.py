#!/usr/bin/env python3
"""Install the trident-loop skill into a host CLI's skills directory.

Primary installation is through each host's plugin system (see README):
Claude Code plugin marketplaces, Kimi Code's /plugins panel and qwen-code
extensions all read the manifests in this repository directly. This script
exists for hosts and workflows that install skills as plain directories.

Usage:
    python install.py --host claude            # copy to ~/.claude/skills
    python install.py --host codex             # copy to ~/.agents/skills
    python install.py --host kimi --dir PATH   # explicit target directory
    python install.py --host claude --link     # symlink instead of copy

Stdlib only. Safe to re-run: replaces an existing trident-loop directory.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent / "skills" / "trident-loop"

HOSTS = {
    # Verified personal-skills directories.
    "claude": ("~/.claude/skills", True),
    "codex": ("~/.agents/skills", True),
    # Best-effort: install primarily through the plugin/extension system and
    # use --dir if your build uses a different skills directory.
    "kimi": ("~/.kimi-code/skills", False),
    "qwen": ("~/.qwen/skills", False),
    # opencode also discovers ~/.claude/skills and ~/.agents/skills (and
    # .opencode/skills per project); ~/.config/opencode/skills is its native
    # global location.
    "opencode": ("~/.config/opencode/skills", False),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, choices=sorted(HOSTS) + ["dsh"],
                        help="Host CLI to install into.")
    parser.add_argument("--dir", help="Explicit target skills directory (overrides the host default).")
    parser.add_argument("--link", action="store_true", help="Symlink instead of copy (for development).")
    args = parser.parse_args()

    if args.host == "dsh":
        print("DeepSeek Harness (dsh) has no native skills directory.\n"
              "Use dsh as reviewer/builder/inspector (it needs no host-side install),\n"
              "or host the loop in dsh by pointing AGENTS.md at the skill:\n\n"
              "    trident-loop: Harden plans with independent review across providers.\n"
              "    Read skills/trident-loop/SKILL.md and follow its phases.\n")
        return 0

    default, verified = HOSTS[args.host]
    target_root = Path(args.dir).expanduser() if args.dir else Path(default).expanduser()
    if not verified and not args.dir:
        print(f"note: the default {args.host} skills directory is best-effort; "
              "prefer the plugin/extension install (see README) or pass --dir.", file=sys.stderr)

    if not SKILL.is_dir():
        print(f"skill not found at {SKILL}; run this script from the repository root.", file=sys.stderr)
        return 1

    target_root.mkdir(parents=True, exist_ok=True)
    dest = target_root / "trident-loop"
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or not dest.is_dir():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    if args.link:
        dest.symlink_to(SKILL, target_is_directory=True)
        print(f"linked {dest} -> {SKILL}")
    else:
        shutil.copytree(SKILL, dest)
        print(f"installed {dest}")
    print(f"next: open a new {args.host} session and invoke the trident-loop skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
