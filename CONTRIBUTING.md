# Contributing to gato

Thanks for your interest in improving `gato`! Whether it's a bug fix, a new
service, docs, or a question - you're welcome here.

## Ground rules

- Be kind. This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- By contributing, you agree your work is licensed under the project's
  [Apache 2.0 license](LICENSE).

## Development setup

`gato` uses [`uv`](https://github.com/astral-sh/uv) for environments and
[`ruff`](https://github.com/astral-sh/ruff) + [`mypy`](https://mypy-lang.org/)
for quality gates.

```bash
git clone https://github.com/proxyroot/gato
cd gato

make install     # creates .venv, installs gato[dev], sets up pre-commit
make check       # ruff + ruff format --check + mypy + pytest
```

Individual gates:

```bash
make lint        # ruff check .
make format      # ruff format .
make type        # mypy
make test        # pytest
make cov         # pytest with coverage
```

## Branching & release strategy

`gato` uses a simple **trunk-based** workflow:

- **`main` is always releasable** - CI (ruff + mypy + tests on Python
  3.10-3.13) must be green on every commit. Never push directly to `main`.
- **Short-lived branches** off `main`, one per change. Name them by intent:
  - `feat/<topic>` - a new service or feature
  - `fix/<topic>` - a bug fix
  - `docs/<topic>`, `chore/<topic>`, `refactor/<topic>`
  - `<username>/<topic>` is also fine for personal forks.
- **Pull requests** target `main`, require passing CI and at least one review,
  and are **squash-merged** so `main` keeps a linear, one-commit-per-change
  history. Keep the PR title in the imperative mood (it becomes the commit
  subject).
- **No long-lived branches** and no merge commits on `main`.

### Releases (maintainers)

We follow [Semantic Versioning](https://semver.org/):

1. Update `__version__` in `src/gato/__init__.py` and move the `Unreleased`
   section of [`CHANGELOG.md`](CHANGELOG.md) under the new version.
2. Tag the release: `git tag vX.Y.Z && git push origin vX.Y.Z` (or publish a
   GitHub Release).
3. The [`release` workflow](.github/workflows/release.yml) builds the
   distributions and publishes to PyPI via Trusted Publishing - no tokens.

## Making a change

1. Fork (or branch, if you're a maintainer) and create a branch off `main`
   following the naming above: `git checkout -b feat/pubsub`.
2. Write code **and tests**. Every behavior should be covered by a test that
   exercises the real google-cloud client through the mock.
3. Run `make check` until it's green.
4. Commit with a clear message and open a pull request against `main`.

Pre-commit runs ruff (lint + format) and mypy automatically on `git commit` once
you've run `make install`.

## Adding a new service

This is the most valuable kind of contribution and is intentionally mechanical.
A service is three files under `src/gato/services/<name>/`:

- `models.py` - a `BaseBackend` subclass holding in-memory state, plus a
  `BackendDict`.
- `responses.py` - a `BaseResponse` subclass with one method per API call.
- `urls.py` - `url_bases` and `url_paths` mapping requests to those methods.

See **[docs/contributing-a-service.md](docs/contributing-a-service.md)** for a
step-by-step walkthrough, and the existing `storage`/`secretmanager` services as
references.

## Reporting bugs & requesting features

Use the [issue templates](https://github.com/proxyroot/gato/issues/new/choose).
For security issues, see [SECURITY.md](SECURITY.md) - please do **not** open a
public issue.

## Code style

- Formatting and linting are enforced by ruff; don't hand-format.
- Public functions and classes get docstrings and type hints.
- Keep handlers small and readable; match the surrounding code.
