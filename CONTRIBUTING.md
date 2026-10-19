# Contributing

Thanks for helping. This is a small, free project maintained on a best-effort basis.

## Before you open a PR

- Open an issue first for anything larger than a bug fix, so we can agree on the approach.
- Keep the runner dependency-free: standard library only, Python 3.10+.
- Run the suite. It uses fake CLI processes and spends no model quota:

  ```
  python -m unittest discover -s skills/trident-loop/scripts -t skills/trident-loop/scripts -v
  ```

- Add or update tests for any change to a provider profile, boundary, parser or approval rule.

## Adding a provider

Implement one boundary profile in `skills/trident-loop/scripts/runner.py` (launch flags, stream parsing, resume semantics), register it, cover it with fake-CLI tests, and document its boundary and live-verification status in `skills/trident-loop/references/runtime.md` and the README table. Never mark a provider live-tested unless you ran it against the real CLI; say which CLI version and model you used.

## Security

Changes that loosen a provider's permission boundary need a clear justification in the PR. Report vulnerabilities privately; see [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contribution is licensed under the MIT License of this repository.
