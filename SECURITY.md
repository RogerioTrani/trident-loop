# Security

## Trust model

trident-loop has no sandbox of its own. It starts other coding-agent CLIs as subprocesses, and each of those sessions is contained only by that CLI's own permission boundary. For each mode, the runner uses the strictest boundary the CLI offers:

| Provider | Review / Inspect | Build |
|---|---|---|
| Claude | `--safe-mode`, tools limited to `Read,Glob,Grep`, no MCP servers | `--permission-mode acceptEdits`; commands keep your normal permission rules |
| Codex | `-s read-only` | `-s workspace-write` with `approval_policy="never"` |
| Kimi | agent-file tool allowlist; the runner rejects any call outside it or outside the repo | build allowlist from the agent file |
| DeepSeek (`dsh`) | `DSH_PERMISSION_MODE=read-only` | `DSH_PERMISSION_MODE=workspace-write` |
| Qwen | `--safe-mode` + `--exclude-tools`, audited stream | `--approval-mode yolo` |
| OpenCode | `plan` agent + the runner's audit of tool calls in the JSON stream | `build` agent with `--auto` |
| OpenCode paste-only | no files or tools offered: plan and diff pasted into the prompt, empty temporary working directory, JSON-only reply | not supported |

The OpenCode `plan` agent's permission asks did not reliably stop tool calls in live runs, and neither did a `deny` permission passed through `OPENCODE_CONFIG_CONTENT`. For OpenCode, the runner's audit is the boundary that counts. `opencode-paste` runs under OpenCode's default agent, which still has tools. The repository is not its working directory and nothing is attached, but a model could still reach a file by absolute path, and plain-text output gives the runner nothing to audit. The paste-only review sees only what is pasted: the plan, plus the diff for an inspection.

In build mode the builder writes to your working tree without asking before each action. Codex runs with `approval_policy="never"`, Qwen with `--approval-mode yolo` and OpenCode with `--auto`, so any of them can edit files and run commands without confirmation. Codex stays inside its `workspace-write` sandbox. Qwen has no filesystem sandbox at all, because `--safe-mode` only disables extensions, MCP servers and hooks.

Use build mode only:

- in a repository you can reset (commit or stash first, or better, use a dedicated worktree);
- with no production credentials in the environment the CLIs inherit;
- on code and plans you are willing to let an agent act on.

Review and inspection are read-only, but they still send repository content to the provider that runs them. Don't delegate code you are not allowed to share with that provider.

The runner never calls hosted APIs and never reads or stores API keys. Each CLI handles its own sign-in. Boundary details and the verification status of each provider are in [`skills/trident-loop/references/runtime.md`](skills/trident-loop/references/runtime.md).

## Reporting a vulnerability

Report security issues privately with GitHub's "Report a vulnerability" button, under Security → Advisories in this repository. Please don't open a public issue for them. Include the provider, the CLI version, the mode and the steps to reproduce. This is a free project maintained on a best-effort basis, so reports get an acknowledgement but no promised fix date.

## Supported versions

Only the latest release gets fixes.
