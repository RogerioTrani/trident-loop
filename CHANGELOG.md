# Changelog

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [0.11.0] - 2026-11-16

### Added
- `opencode-paste`, a paste-only OpenCode profile for review and inspection. The plan and, for an inspection, the diff are pasted into the prompt, nothing is attached, and the CLI starts in an empty temporary directory that must still be empty at the end. The reply must be the JSON review alone, and any other text, invalid JSON or a failed schema check refuses the run. It runs `run -m <model>` with the prompt on stdin and plain-text output. On Windows the default executable is the OpenCode Desktop CLI, which holds the Desktop login, and the default model is `opencode/beam-free`; `--cli` and `--model` override both. It has no build mode and no native resume: a continuation round pastes the prior review.
- Fake-CLI tests for the new profile: empty working directory, pasted plan and diff, refusal of tool traces, prose, file-read requests, invalid JSON, writes into the working directory, `--effort` and build mode. The suite now has 93 tests.

### Changed
- README, SECURITY.md, SKILL.md and `references/runtime.md` now say what was actually tested with OpenCode. Two live reviews under the `plan` agent called `bash` and read files and were refused by the runner's audit, and the `ask` rule is no longer described as a boundary that fails closed. One live plan review completed through `opencode-paste`. SECURITY.md gained the OpenCode rows it was missing.
- A provider without native resume now receives the prior review in the prompt on a continuation round. Kimi already did; this applies the same rule to `opencode-paste`.
- Plugin manifests now carry the release version; they still said 0.9.0 in the 0.10.0 release.

## [0.10.0] - 2026-11-07

### Added
- OpenCode (`opencode`) as a sixth registered provider: `plan` agent boundary for review/inspect (permission asks auto-reject headless) plus a `tool_use` deny-list audit of the `--format json` stream, `build` agent with the CLI's `--auto` for builds, `--session` resume and `--variant` effort pass-through. The runner requires opencode 1.18.0 or newer.
- `install.py --host opencode` targeting `~/.config/opencode/skills`.

## [0.9.0] - 2026-10-19

First public release.

### Added
- A provider registry with a boundary profile for each of Claude Code, Codex, Kimi Code, DeepSeek Harness (`dsh`) and qwen-code. Upstream claudex-loop supports Claude and Codex.
- Default roles taken from the pipeline order `claude → codex → kimi → deepseek → qwen`. Deviations and reviewer swaps between rounds are recorded in the log.
- A shared runner with `review`, `build` and `inspect` modes. It validates structured reviews and ties each approval to the plan's SHA256.
- Packaging for several hosts: a Claude Code marketplace entry, Codex and Kimi plugin manifests, a Gemini/qwen extension manifest and `install.py`.
- A test suite that runs against fake CLI processes, in CI on Windows, macOS and Linux.

[0.11.0]: https://github.com/RogerioTrani/trident-loop/releases/tag/v0.11.0
[0.10.0]: https://github.com/RogerioTrani/trident-loop/releases/tag/v0.10.0
[0.9.0]: https://github.com/RogerioTrani/trident-loop/releases/tag/v0.9.0
