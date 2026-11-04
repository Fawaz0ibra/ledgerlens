# 0004. Build the API image in two stages on python:3.12-slim

- **Status:** Accepted
- **Date:** 2026-11-04

## Context

The API has to run the same way on this machine, in CI (lesson 1.5) and on Kubernetes (Module 7), so
it ships as a container image. The image is downloaded on every deploy and to every new node, and
everything in it has to be kept patched. It now talks to Postgres. Later images will carry PyTorch,
so the pattern set here will be reused.

## Decision

- A two-stage Dockerfile. The build stage installs the locked dependencies and our package into
  `/app/.venv` with uv 0.13.5 (`--no-dev`, `--no-editable`, uv's cache in a build cache mount). The
  runtime stage copies only that environment.
- Both stages on `python:3.12.16-slim-trixie`, pinned by digest. The service runs as user 10001
  (numeric, not root), and the code is owned by root, so the service can't change it.
- The build context is an allowlist: `pyproject.toml`, `uv.lock`, `README.md` and `src/` only.
- Postgres driver `psycopg[binary]` 3.3.6 with psycopg-pool 3.3.3, so no stage needs a compiler or libpq.

## Rejected options

- **One stage:** measured below. It ships uv, the source tree and, as usually written, the dev tools,
  and runs as root.
- **`python:3.12.16-trixie` (the full image):** 411.8 MB compressed against 43.3 MB for slim, for
  compilers and headers the service never uses.
- **`python:3.12.16-alpine`:** 18.0 MB compressed, but Alpine's C library (musl) isn't the one most
  Python wheels are built for, and the ML images in later modules (PyTorch, vLLM) have no wheels for it.
  One base family for every LedgerLens image is worth more than 25 MB.
- **`gcr.io/distroless/python3-debian13`:** no shell and no package manager, but it ships Debian's
  Python 3.13, and our lock is for 3.12.
- **`psycopg[c]`** (built against the system's libpq): psycopg's docs call it the preferred install for
  production, because operating-system updates then patch libpq. It needs a compiler and libpq-dev in
  the build stage and libpq at runtime; we take the binary for now.

## Measurements

| Image (linux/amd64) | Compressed | On disk |
|---|---|---|
| One stage, `uv sync` with the dev tools | 74.1 MB | 299 MB |
| The build stage on its own | 75.0 MB | 298 MB |
| **Two stages (chosen)** | **56.2 MB** | **236 MB** |
| Two stages, after adding psycopg | 62.2 MB | 264 MB |

- Of the chosen image's 179.5 MB unpacked, 134 MB is the base (Debian 87.7, Python 41.4, system
  packages 4.9) and 45.4 MB is our environment. The biggest package is uvloop, at 16 MB.
- The two-stage saving is almost all uv itself (41 MB on disk). The dev tools were 8.2 MB, and uv's
  cache added only about 2 MB, because uv hardlinks the same files into the cache and the environment.
- Build: 18.4 s from cold, base download included. Dependencies 2.6 s, our package 0.5 s; when only
  the code changes, only the 0.5 s step reruns.
- `docker stop`: 0.6 s. Uvicorn is process 1, gets the stop signal and runs the shutdown hook.

Runs on 2026-11-03 and 2026-11-04: Docker Desktop 4.97.0 (engine 29.9.2, containerd image store), WSL2
Ubuntu 24.04, Ryzen 5 3600X. The code is the commit that adds this record. The full and Alpine sizes
are Docker Hub's figures for linux/amd64, not our builds.

## Consequences

- The base is three quarters of the image, so the next real cut in size is the base, not the Dockerfile.
- The base still has pip 25.0.1 (6.8 MB): an installer remains in the image we run.
- Security fixes to libpq and OpenSSL arrive only with a new psycopg-binary, and the base's only with a
  new digest. Both need a bot that opens upgrade pull requests (Dependabot, lesson 8.3).
- `uvicorn[standard]` brings packages we don't use: websockets (1.9 MB), pyyaml (3.1 MB) and watchfiles.
- The tests need Docker: testcontainers starts the same Postgres image for the suite (5.4 s, of which
  3.2 s is Postgres starting).

## Revisit when

- Trivy (lesson 8.3) finds vulnerabilities in the base that a slim update doesn't fix: compare hardened
  minimal bases by their scan results.
- A libpq or OpenSSL fix is out in Debian but not yet in psycopg-binary: switch to `psycopg[c]`.
- Module 4 adds PyTorch: measure again. The CUDA libraries alone were 5.75 GB in lesson 0.3.
- We move to Python 3.13: distroless becomes possible.
