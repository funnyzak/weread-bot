# Repository Guidelines

## Project Structure & Module Organization
Main automation logic lives in `weread-bot.py`, orchestrating scheduling, reading simulation, and notifications. Configuration templates (`config.yaml.example`) stay at the root; copy to `config.yaml` for local overrides. Docs and deployment references belong under `docs/`, persistent logs under `logs/`, and disposable experiments or generators inside `tmp/` to keep history clean.

## Build, Test, and Development Commands
- `python -m venv venv && source venv/bin/activate`: provision the Python 3.9+ environment expected by schedulers and HTTP clients.
- `pip install -r requirements.txt`: install runtime dependencies (requests, schedule, apprise, PyYAML, urllib3).
- `python weread-bot.py --config config.yaml --verbose`: run an immediate session with explicit config and expanded logging for debugging.
- `python weread-bot.py --mode scheduled --config config.yaml`: exercise the cron-driven path and confirm the schedule block parses correctly.
- `python weread-bot.py --mode daemon --config config.yaml`: validate long-lived loops, session intervals, and graceful signal handling.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation, snake_case functions, and PascalCase dataclasses or enums. Extend the existing dataclasses instead of injecting bare dicts so validation stays centralized. Reuse module-level constants for defaults, add type hints on new functions, and route diagnostics through the configured logger rather than `print`. Align YAML keys and examples with the provided templates.

## Testing Guidelines
There is no dedicated unit-test suite yet; rely on scenario-driven runs. Use anonymized CURL payloads and short `TARGET_DURATION` windows (5-10 minutes) when iterating locally, then inspect `logs/weread.log` for retry cadence, notification output, and multi-user sequencing issues. When extending notification transports or scheduling, outline the manual test matrix and attach relevant log excerpts in the PR.

## Commit & Pull Request Guidelines
Use Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) as demonstrated in recent history. Each PR should explain the motivation, reference related issues, list new environment variables or config keys, and include reproduction steps plus verification evidence (command snippets or screenshots for doc changes). Keep PRs scoped to a single concern and update affected docs such as `docs/github-action-autoread-guide.md`.

## Security & Configuration Tips
Never commit CURL strings or API tokens; load them via environment variables like `export WEREAD_CURL_BASH_FILE_PATH=/secure/curl.txt` or GitHub Actions secrets. Store per-user overrides under `config.yaml`'s `curl_config.users` array, scrub logs before sharing, rotate cookies regularly, and keep any `.env` files outside version control.
