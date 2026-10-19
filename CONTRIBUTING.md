# Contributing

Thanks for your interest. This is a small, free project maintained on a best-effort basis, so reviews may take a while.

## Before you open a PR

- For anything bigger than a bug fix, open an issue first so we can agree on the approach.
- Keep the runner on the standard library only, with Python 3.10 as the minimum.
- Run the suite. It uses fake CLI processes and spends no model quota:

  ```
  python -m unittest discover -s skills/trident-loop/scripts -t skills/trident-loop/scripts -v
  ```

- If you change a provider profile, a boundary, a parser or an approval rule, add or update its tests.

## Adding a provider

Implement one boundary profile in `skills/trident-loop/scripts/runner.py` (launch flags, stream parsing, resume semantics) and register it. Cover it with fake-CLI tests, then document its boundary and live-verification status in `skills/trident-loop/references/runtime.md` and in the README table. Mark a provider live-tested only after you ran it against the real CLI, and say which CLI version and model you used.

## Security

If a PR loosens a provider's permission boundary, explain why in the description. Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

Contributions are accepted under the repository's MIT License.
