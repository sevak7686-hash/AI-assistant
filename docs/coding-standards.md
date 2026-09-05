# Coding Standards

## Naming

- Use `snake_case` for modules, functions, methods, and local variables.
- Use `PascalCase` for classes, protocols, and exceptions.
- Use `UPPER_SNAKE_CASE` for module constants.
- Name booleans with a predicate such as `is_`, `has_`, or `can_`.
- Prefer descriptive names over abbreviations; do not use one-letter names outside a small loop
  or mathematical expression.

## Python style

- Target Python 3.11 or newer and add type annotations to public functions and methods.
- Keep application code dependent on domain types and protocols, not Telegram or provider clients.
- Use `async` APIs for network and database operations.
- Keep functions focused and avoid unrelated refactoring in feature changes.
- Run `ruff check .`, `ruff format --check .`, and `pytest` before opening a pull request.

## Docstrings

- Add docstrings to public modules, classes, protocols, and functions when their purpose or
  contract is not obvious from the signature.
- Use imperative, concise first lines: `Return the assistant reply.`
- Document parameters, return values, and exceptions only when they add information not clear from
  the type signature.
- Do not add comments that merely restate the code.

## Commit messages

- Use an imperative subject no longer than 72 characters.
- Start the subject with one of: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Keep the subject focused on the behavior or artifact changed, for example:
  `docs: define application API contract`.
- Add a body when context, migration steps, or compatibility impact needs explanation.

## Pull-request review

- Open pull requests into `dev`, not `main`.
- Keep each pull request focused and describe behavior, configuration or migration changes, and
  validation performed.
- Require passing CI and at least one teammate approval before merging.
- Review correctness, security, API compatibility, tests, and operational impact before style.
- Resolve review comments or explain the chosen alternative before merging.
- Do not commit secrets, `.env` files, generated output, or unrelated formatting changes.