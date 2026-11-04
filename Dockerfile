# The LedgerLens API image, built in two stages. From the repo root:
#
#     docker build -t ledgerlens-api:dev .
#
# Stage 1 (build) installs everything with uv. Stage 2 (runtime) starts again from a clean base and
# takes only the finished virtual environment, so uv, its cache and the source tree never reach the
# image we run.

# Python 3.12.16 on Debian trixie, pinned by digest. Both stages use the same base because the virtual
# environment points at /usr/local/bin/python3.12: the interpreter must be at that path in both.
FROM python:3.12.16-slim-trixie@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /bin/uv

# copy: the cache mount is a different filesystem, so hardlinks can't work.
# compile bytecode: the service user can't write .pyc files next to the code at runtime, so write them now.
# downloads never: use the base image's Python; fail loudly instead of fetching another one.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Third-party dependencies first: no dev tools (--no-dev) and not our own package yet
# (--no-install-project). This layer is rebuilt only when pyproject.toml or uv.lock change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

# Then our package. --no-editable installs a copy into the environment instead of a link back to src/,
# so the environment works on its own once it leaves this stage.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.12.16-slim-trixie@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS runtime

LABEL org.opencontainers.image.title="ledgerlens-api" \
      org.opencontainers.image.source="https://github.com/Fawaz0ibra/ledgerlens" \
      org.opencontainers.image.licenses="Apache-2.0"

# A system user with a fixed numeric ID, no home and no login shell. Kubernetes can check that a
# numeric ID isn't 0 (root) before it starts the container; it can't check a name.
RUN groupadd --system --gid 10001 ledgerlens \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin ledgerlens

# Owned by root, readable by everyone: the service can run its code but can't change it.
COPY --from=build /app/.venv /app/.venv

# unbuffered: each log line reaches `docker logs` when it's written, not when a buffer fills.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER 10001:10001
EXPOSE 8000

# Exec form (a JSON list): Uvicorn is process 1 and gets docker stop's SIGTERM itself, so it shuts down
# cleanly. 0.0.0.0: listen on the container's network interface; 127.0.0.1 would be reachable only
# from inside the container.
CMD ["uvicorn", "ledgerlens.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
