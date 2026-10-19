# Security

## Trust model

trident-loop does not sandbox anything itself. It launches other coding-agent CLIs as subprocesses, and each delegated session is only as contained as that CLI's own permission boundary. The runner picks the strictest boundary each CLI offers for the mode it runs in:

| Provider | Review / Inspect | Build |
|---|---|---|
| Claude | `--safe-mode`, tools limited to `Read,Glob,Grep`, no MCP servers | `--permission-mode acceptEdits`; commands keep your normal permission rules |
| Codex | `-s read-only` | `-s workspace-write` with `approval_policy="never"` |
| Kimi | agent-file tool allowlist; the runner rejects any call outside it or outside the repo | build allowlist from the agent file |
| DeepSeek (`dsh`) | `DSH_PERMISSION_MODE=read-only` | `DSH_PERMISSION_MODE=workspace-write` |
| Qwen | `--safe-mode` + `--exclude-tools`, audited stream | `--approval-mode yolo` |

**Build mode writes to your working tree without asking per action.** Codex runs with `approval_policy="never"` and Qwen runs with `--approval-mode yolo`, so the builder can edit files and run commands without confirmation. Codex stays inside its `workspace-write` sandbox; Qwen has no filesystem sandbox (`--safe-mode` only disables extensions, MCP servers and hooks). Run build mode only:

- in a repository you can reset (commit or stash first; a dedicated worktree is better);
- with no production credentials in the environment the CLIs inherit;
- on code and plans you are willing to let an agent act on.

Review and inspection modes are read-only by design, but they still send repository content to whichever provider runs them. Do not delegate code you are not allowed to share with that provider.

The runner never calls hosted APIs and never reads or stores API keys; authentication stays inside each CLI. See [`skills/trident-loop/references/runtime.md`](skills/trident-loop/references/runtime.md) for each provider's boundary details and verification status.

## Reporting a vulnerability

Please report security issues privately through GitHub's **Report a vulnerability** button (Security → Advisories) on this repository rather than in a public issue. Include the provider, CLI version, the mode, and the steps to reproduce. This is a free, best-effort project: expect an acknowledgement, not an SLA.

## Supported versions

Only the latest release receives fixes.
