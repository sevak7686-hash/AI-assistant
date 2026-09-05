# Contributing

See [docs/coding-standards.md](docs/coding-standards.md) for naming, docstrings, commit
messages, and review expectations.

## Branches

- `main` is the stable branch. Do not push directly to it.
- `dev` is the integration branch for completed, reviewed work.
- Create short-lived branches from `dev`: `feature/<name>`, `fix/<name>`, or `chore/<name>`.
- Open a pull request into `dev`, wait for CI and one teammate review, then delete the feature branch after merge.
- Periodically open a reviewed pull request from `dev` into `main` for a release.

When starting work:

```powershell
git switch dev
git pull --ff-only
git switch -c feature/short-description
```

## Pull requests

Keep each pull request focused. Describe the behavior changed, configuration or migration steps, and how it was tested. Do not include secrets, `.env` files, generated build output, or unrelated formatting changes.

Required checks are:

```powershell
ruff check .
ruff format --check .
pytest
```

## Secrets and DeepSeek

Create a local `.env` from `.env.example`. Store `DEEPSEEK_API_KEY` only there or in the team secret manager. If a key is exposed, revoke it immediately and issue a replacement. The key owner should share access through the team secret manager rather than sending the raw key to teammates.