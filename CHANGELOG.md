# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.9.0] - 2026-10-19

First public release.

### Added
- Provider registry with per-provider boundary profiles for Claude Code, Codex, Kimi Code, DeepSeek Harness (`dsh`) and qwen-code, extending upstream claudex-loop's two providers to five.
- Role resolution from the pipeline order `claude → codex → kimi → deepseek → qwen`, with recorded deviations and reviewer swaps between rounds.
- Shared runner (`review`, `build`, `inspect`) that validates structured reviews and binds approvals to the plan's SHA256.
- Multi-host packaging: Claude Code marketplace, Codex and Kimi plugin manifests, a Gemini/qwen extension manifest, and `install.py`.
- Test suite driven by fake CLI processes, run in CI on Windows, macOS and Linux.

[0.9.0]: https://github.com/RogerioTrani/trident-loop/releases/tag/v0.9.0
