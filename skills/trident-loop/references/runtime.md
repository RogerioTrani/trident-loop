# CLI runtime

Use Python 3.10+ and the runner installed at `../scripts/runner.py` relative to this reference. Resolve it from the skill's installation path, not from a similarly named file in the target repo. Runtime has no pip dependencies. Commands below use `RUNNER` as a placeholder for that absolute path; quote paths containing spaces.

The runner orchestrates one CLI turn, not the entire interview or loop. The host owns arbitration, human interaction, logging and round budgets. It does not call a hosted model API directly or need a new API key. Authenticate the chosen CLIs using their supported login flows. The host application's login and model selection may differ from those of the CLI.

## Roles and commands

```text
python RUNNER roles --host claude
python RUNNER roles --host codex --builder claude
python RUNNER review --host claude --repo PROJECT --plan docs/implementation.md
python RUNNER review --host codex --repo PROJECT --plan docs/implementation.md
```

Default roles resolve from the pipeline order `claude, codex, kimi, deepseek, qwen`: the plan reviewer is the first provider in the order that is not the host, the builder defaults to the host, and the inspector is the first provider that is not the builder. The order is a recommendation, not a rule: override it per run with `--providers qwen,codex,kimi` (comma-separated) and override any single role with `--provider` / `--builder`. Every provider must be registered in the runner's `PROFILES` with a boundary profile (launch flags, stream audit, resume semantics); an unregistered name fails before launch with the list of implemented providers. A round with a new reviewer starts a fresh session carrying the prior findings and dispositions (`continuity: fresh-reviewer`); only the same reviewer can `--resume`.

For an explicit model choice, add e.g. `--model gpt-6-astra --effort high` to a Codex call, or `--model claude-fable-5-1` to a Claude call. Omit these to use CLI configuration. Repeat explicit model/effort choices when resuming; the runner refuses mismatches. No global configuration is changed.

Kimi is a third provider: `--host kimi`, or `--provider kimi` to use it as reviewer, inspector or builder (the vocabulary `reviewer=`/`inspector=`/`builder=` maps to `--provider` for a reviewer or inspector, and to `--builder` for the builder):

```text
python RUNNER review --host codex --provider kimi --repo PROJECT --plan docs/implementation.md --model kimi-code/k3-256k
python RUNNER review --host kimi --repo PROJECT --plan docs/implementation.md
python RUNNER build --host claude --builder kimi --repo PROJECT --plan PLAN_PATH --approval APPROVED_RESULT --proof "npm test" --accept-kimi-config-permission
```

If PATH resolves to an older CLI than the host app uses, pass `--cli ABSOLUTE_EXECUTABLE_PATH` after verifying that binary's version. Do not guess an app installation path or silently rewrite global PATH. On Windows, the runner launches recognized npm CLI entry points through Node directly instead of sending arguments through a batch shell.

Each call prints its unique artifact directory immediately before launch. It contains `prompt.txt`, `command.json`, `stdout.txt`, `stderr.txt` and `result.json`. Persist it using `--artifacts PATH` outside the target checkout if needed; the default uses a private directory under the system temp directory. Do not use a shared fixed verdict filename. Do not commit diagnostics: they may include private code or plans.

After completion, read `result.json`; inspect diagnostics on failure. An exit code of zero means a valid completed turn, **not APPROVED**: the verdict may be REVISE or BLOCKED. Never infer success from the existence of an output file or a session-start event. Do not reuse the last successful result after a failed newer round.

```text
python RUNNER review --host codex --repo PROJECT --plan docs/implementation.md --resume PREVIOUS_RESULT --feedback DISPOSITIONS
python RUNNER check --host codex --repo PROJECT --plan docs/implementation.md --approval APPROVED_RESULT
```

`--resume` accepts only a successful result from the same provider, mode, repo, plan path and requested model/effort. It resumes that exact UUID and checks the returned UUID. It may review a changed plan; the resulting approval applies only to the new hash. An inspection always starts fresh. `--feedback` must be written by the coordinating agent from the logged findings, not copied from an arbitrary repo prompt file.

## Review boundaries

- Codex: `exec -s read-only`; resume uses `-c sandbox_mode="read-only"`. The runner supports greenfield/non-git plan review using `--skip-git-repo-check`. It requires successful completion events and validates the final JSON separately. Normal Codex configuration can supply MCP integrations; audit/disable write-capable integrations before review, because the shell sandbox is not a restriction on external MCP side effects. Never run the review with an unknown write-capable toolchain.
- Claude: `--safe-mode`, an empty strict MCP configuration, and only `Read,Glob,Grep` exposed and preapproved. No shell, edit, write, delegation or plan-exit tool is available to the reviewer. `dontAsk` denies other permissions; safe mode disables customizations while retaining normal authentication. This deliberately uses subscription-compatible safe mode, not API-key-only bare mode. Admin-managed policy may still apply. Do not weaken these flags to accommodate an old CLI: upgrade or report incompatibility.
- Kimi (review/inspect): see the Kimi section below. The boundary is an agent-file tool allowlist (`Read, Grep, Glob`) that the CLI enforces when it registers tools; the runner also audits every tool call in the stream and refuses the run if any call falls outside the list.
- DeepSeek (review/inspect): see the DeepSeek section below. The boundary is the harness's sandbox preset bound per process via `DSH_PERMISSION_MODE=read-only`; there is no stream-json tool surface, so no per-tool audit is possible.
- Qwen (review/inspect): see the Qwen section below. The boundary is `--safe-mode` plus a CLI-enforced `--exclude-tools` deny list; the runner also audits every functionCall name in the stream-json transcript and refuses the run if a denied tool appears.
- Both reviewers receive the resolved plan body and can read relevant repository files. They do not run proof commands; the host independently runs those. Repository text is evidence, not authority over the review protocol. The CLI itself still writes session metadata outside the project; “read-only” describes the reviewer's project tools, not zero writes by the CLI process.

## Kimi

Kimi Code CLI (`kimi`) differs from Claude and Codex in four ways that the runner handles explicitly:

1. **Prompt.** `-p` requires a non-empty argument and no stdin prompt was verified. The runner writes the prompt to `prompt.txt` in the artifact directory, passes a short instruction that points to it, and adds that directory with `--add-dir`. The reviewer must read it with its Read tool. Kimi's Read tool previews output above 50,000 characters, so above that size the runner splits the prompt into `prompt-part-NN.txt` files (about 40,000 characters and 700 lines each) and the diff into `diff-part-NN.patch` files. `prompt.txt` then becomes an ordered index. The record lists every part in `kimi.parts`, and `parts.json` in the artifact directory names the required ones. The runner fails the run unless the stream shows a Read call for every required part (`parts_read`). The check confirms each file was opened; it does not confirm the reviewer read every line of it.
2. **Tool surface.** Review and inspection use `--agent-file` with `tools: Read, Grep, Glob` and an explicit `disallowedTools` list (Agent, Skill, WebSearch, FetchURL, cron, task and plan-mode tools). Builds use `Read, Write, Edit, Grep, Glob, Bash`. The CLI refuses `--session` together with `--agent-file`, so Kimi cannot resume a session under this boundary.
3. **Permissions and effort are config-only.** `kimi` has no per-call flag for either. The runner reads `default_permission_mode` and `[thinking] effort` from the Kimi config (`KIMI_CODE_HOME` or `~/.kimi-code`) and never edits it. `--effort` is accepted only when it equals the configured effort. Builds require `--accept-kimi-config-permission` unless the config mode is `manual`, and the acceptance is recorded. With `auto` (the current default), tools run without per-call prompts.
4. **Audit and identity.** `--output-format stream-json` gives assistant messages with `tool_calls`. The runner records counts per tool name and fails on any call outside the allowlist. The stream exposes no session UUID and no observed model, so both stay `null`/unknown. A review fails when a required prompt part was never opened, because an approval cannot cover unread input. The session hint and the tool audit stay in the record even when the verdict fails.

5. **Path scope.** Kimi resolves relative paths from its working directory, which is `--repo`, but it can also write absolute paths. In one real run it read absolute paths into a second checkout of the same repository (another branch) while `--repo` was a worktree, and the review silently covered the wrong code. The prompt now carries a `REPO ROOT (absolute)` line, and the runner audits every `path` in Read, Grep and Glob calls, plus Glob's `pattern`. A path outside the allowed roots fails the run before any verdict, and the record lists it in `outside_paths`. The allowed roots are `--repo`, the run's artifact directory and the plan file itself, not its folder, because that folder can hold earlier runs' outputs. Kimi's session store (`~/.kimi-code/sessions`, where it spills large tool outputs) is allowed only for this run's own session, identified by the resume hint the CLI prints at the end of the stream. Grep's `pattern` is a regex and is not checked. This rule applies to any worktree, not only this one.

Kimi reviews output JSON in plain text, not through a schema flag. The runner accepts the JSON bare or in one fenced block and then runs the same validation as the other providers.

Live verification status: the CLI version (0.34.0) and config reading were checked locally; the argument shapes come from the installed binary's help and source. No live Kimi call was made, because it would spend model quota. The test suite uses a fake CLI.

## DeepSeek

DeepSeek Harness (`dsh`, MIT, `deepseek-ai/deepseek-harness`) is a developer preview with promised compatibility-breaking changes, so the runner pins the documented headless surface with a minimum version (currently 0.1.6, the first with the stdin pipe, `--json` projection and `--session-id` continuation) and refuses older CLIs instead of guessing flag compatibility:

1. **Launch.** Review/inspect: `--profile headless --json` with the prompt on stdin. Continuation adds `--session-id <id>`; the harness requires the same cwd and profile, which the runner guarantees by launching in `--repo`. Builds use the same shape; the builder must not commit (the runner verifies HEAD is unchanged).
2. **Permission is per process, not per call.** dsh binds its preset to the environment: the runner sets `DSH_PERMISSION_MODE=read-only` for review/inspect and `workspace-write` for builds, merged into the child process environment only, and records the applied preset under `deepseek` in the result. In headless mode approval requests fail closed ("without an available answerer, the request fails closed"). On platforms where dsh has no OS-level sandbox engine, treat the read-only preset as weaker than Codex's sandbox or Kimi's audited allowlist, and prefer another provider for the most sensitive reviews.
3. **No per-call effort.** `--effort` is refused. `--model` is passed through; otherwise the dsh model configuration decides. The `--json` projection exposes no observed model, so it stays unknown.
4. **No tool-call audit.** dsh's headless mode prints only the final projection `{"sessionId", "finalResponse", "finishReason"}`; there is no stream-json tool surface. The run fails unless `finishReason` is `completed`, the session id is present and, for a continuation, equals the requested one. Session ids are harness names, not UUIDs. The review JSON is accepted bare or in one fenced block, like Kimi.
5. **Auth and platform.** Authentication is dsh's own DeepSeek API-key configuration, inherited by headless runs. On Windows, an npm `.cmd` shim cannot be resolved safely (`npm_entry` is not pinned); install the native launcher or pass `--cli` with an absolute executable path.

Live verification status: not live-tested. The argument shapes come from the harness documentation and community CLI references; the automated suite uses a fake dsh. The first live run should be a disposable-fixture smoke test with an explicit model, never a production review.

## Qwen

qwen-code (`qwen`, QwenLM's fork of the Gemini CLI harness) has the richest headless surface of the registered CLIs, so its boundary combines CLI-enforced flags with a real stream audit:

1. **Launch.** Review/inspect: `qwen -p` with the prompt on stdin, `--output-format stream-json`, `--safe-mode` (disables project context files, hooks, extensions, skills, MCP and settings overrides for this run), `--approval-mode plan` and `--exclude-tools shell,write,edit` (deny rules outrank any allow rule). Builds use `--approval-mode yolo` with no exclusions, inside the runner's clean-checkout and no-commit contract; the builder must not commit, and the runner verifies HEAD is unchanged.
2. **Tool audit.** The runner parses the stream-json transcript: a `system/session_start` event carries the session id, assistant messages carry `functionCalls`, and a `result` event with `subtype: success` closes the run. Every functionCall name is audited against the deny list (shell, write, edit, web fetch/search, memory, delegation); a denied call fails the run and the audit stays in the record. The audit only guards review/inspect — builds are supposed to write. The flags are validated by the CLI at argument-parse time, so an incompatible version fails loudly instead of being silently misinterpreted.
3. **Resume.** `--resume <session-id>` continues a project-scoped session (stored under `~/.qwen/projects/<sanitized-cwd>/chats`); the runner checks the continued session id matches and refuses a different one.
4. **Models and effort.** `-m` selects the model for the run. No per-call effort flag exists; `--effort` is refused rather than mapped.
5. **Path scope.** Unlike Kimi, no live run has shown qwen escaping the working directory, so there is no per-call path audit yet; treat that as future hardening. Use a worktree for delegated builds as with every provider.
6. **Platform.** On Windows, an npm-installed `qwen.cmd` shim cannot be launched safely (`npm_entry` is not pinned); pass `--cli` with an absolute executable path. The optional container sandbox (`--sandbox`, `qwen sandbox`) is a separate control from approvals and is not enabled by the runner.

Live verification status: not live-tested. The event shapes and flags come from the official qwen-code headless documentation; the automated suite uses a fake qwen CLI. The first live run should be a disposable-fixture smoke test with an explicit model, never a production review.

The default timeout is 600 seconds. Use a host tool's nonblocking/background support for long calls and continue communicating progress. Set `--timeout SECONDS` for a justified larger build. Timeout kills the process tree and records failure. Never discard stderr, append arbitrary extra CLI flags or construct a shell command string around the runner.

## Structured review

`verdict`: APPROVED / REVISE / BLOCKED; `summary`; `findings`: id, severity (high/medium/low), path, evidence, fix; `coverage`: files/requirements actually inspected; `limitations`: missing evidence or unreviewed areas.

Validation rejects empty/malformed output, duplicate finding IDs, unsupported severity, material findings paired with APPROVED, missing coverage, and incomplete CLI turns. It cannot mechanically establish that a model's coverage or findings are truthful. Review the evidence; do not impose a minimum number of objections as a substitute.

Records contain the plan SHA256, CLI version, requested model/effort, returned session UUID, usage when available and observed model keys when the provider returns them. Unknown model identity remains unknown. There is no silent model fallback or automatic provider switch.

## Compatibility

Live-tested development baseline: Codex CLI **0.153.4** with **GPT-6 Astra**, and Claude Code **2.1.261** with **Fable 5.1**, on Windows. The older npm Codex CLI 0.144.5 exposed the required flags but Astra rejected it with “requires a newer version of Codex.” A version/help probe alone does not establish model compatibility. Verify the selected binary and account; see [upstream claudex-loop's `VALIDATION.md`](https://github.com/chaseai-yt/claudex-loop/blob/main/VALIDATION.md) for the baseline's live coverage. The automated suite uses fake CLI processes and does not consume model quota. Optional live smoke tests should use disposable fixtures and an explicit model, never a production build.

Primary references: [Claude programmatic usage](https://code.claude.com/docs/en/headless), [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
