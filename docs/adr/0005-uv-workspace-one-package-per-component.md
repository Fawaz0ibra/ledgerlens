# 0005. Split the repo into a uv workspace: one package per component

- **Status:** Accepted
- **Date:** 2026-11-09
- **Supersedes:** the one-package part of [0003](0003-fastapi-service-one-package.md)

## Context

ADR 0003 kept all code in one package and named the trigger for splitting it: a component that needs
dependencies the API shouldn't carry. The synthetic invoice generator (lessons 1.6 and 1.7) is that
component. It will render PDF and PNG pages with a headless browser, and Module 4 brings PyTorch. In one
package, each of those would land in the API's environment and its image. The generator must still build
its invoices from the API's own contract, so the two can't drift apart.

## Decision

A uv workspace with one shared `uv.lock`. The root stays the `ledgerlens` package (the API and the
contract). `datagen/` is a second package, `ledgerlens-datagen`, which depends on `ledgerlens` as a
workspace member. The root's `dev` group lists `ledgerlens-datagen`, so `uv sync` gives development and
CI every package, while the image, installed with `--no-dev`, gets the API only. The image build sees
the generator's `pyproject.toml` but not its code, and keeps `uv sync --locked`.

## Rejected options

- **One package, with the generator's dependencies in a dependency group or an extra:** the generator's
  code would still ship inside the API package, and the two would share one version number. The
  generator needs its own version, because dataset cards cite the version that made the data.
- **A separate repository for the generator:** the contract would have to be published and versioned as
  its own package, and every contract change would need a release before the generator could use it.
- **`uv sync --frozen` for the image's dependency step (the pattern in uv's Docker guide):** `--frozen`
  skips checking `uv.lock` against the projects, so an image could be built from a stale lock. Mounting
  the member's `pyproject.toml` keeps `--locked`.
- **A virtual root (no package at the root, the API moved into its own folder):** tidier, but it moves
  every API path (`src/`, the Dockerfile, CI) for no gain today.

## Measurements

| | Before: one package (6f78b68) | After: workspace (03b33d2) |
|---|---|---|
| Packages in `uv.lock` | 52 | 53 (the one added is `ledgerlens-datagen`) |
| API image size, `docker image inspect` | 264,333,882 bytes | 264,333,948 bytes |
| Distributions installed in the API image | 25 | 25, `ledgerlens-datagen` not among them |
| `import ledgerlens_datagen` in the API image | not applicable | `ModuleNotFoundError` |
| Tests, `uv run pytest --cov` | 53 | 85 (32 for the generator), 100% coverage |
| CI on the pull request | | checks 30 s, image 50 s |

The first push of the workspace (25ede92) passed the checks job and failed the image job. The image's
build context held only the root `pyproject.toml`, so `uv sync --locked` stopped with "`ledgerlens-datagen`
references a workspace in `tool.uv.sources` (...), but is not a workspace member". Letting the build see
`datagen/pyproject.toml` fixed it (03b33d2).

Runs on 2026-11-09: uv 0.13.5, Python 3.12.15 (3.12.16 in the image), Docker Desktop 4.97.0 (engine
29.9.2) on WSL2 Ubuntu 24.04, Ryzen 5 3600X; CI on GitHub's `ubuntu-24.04` runners, run 42690668083.

## Consequences

- Each package declares its own dependencies, and `uv lock` resolves them together: a version conflict
  between components shows up when locking, not at runtime.
- The generator has its own version (0.1.0), which the dataset card will cite.
- A new workspace member must be added in several places, or something breaks: `members` and the `dev`
  group in the root `pyproject.toml`; the root's pytest, coverage, mypy and ruff settings; and the image
  build (`.dockerignore` and the dependency step's mounts), as the failed image job showed.
- The generator is installed in CI's `checks` job, so its future dependencies (the browser) make that job
  slower; the API image doesn't change.

## Revisit when

- Module 4 adds a vision package with PyTorch: it becomes another member. If the dev environment grows too
  large for one CI job, move heavy members out of the `dev` group into their own group and CI job.
- A member needs a Python other than 3.12: a uv workspace has one `requires-python` for every member.
