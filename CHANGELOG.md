# Changelog

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

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

[0.10.0]: https://github.com/RogerioTrani/trident-loop/releases/tag/v0.10.0
[0.9.0]: https://github.com/RogerioTrani/trident-loop/releases/tag/v0.9.0
