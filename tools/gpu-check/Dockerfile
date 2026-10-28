# Python 3.12.15 on Debian trixie, pinned by digest (python.org build, same version as our WSL Python).
# No CUDA in the base: torch's wheels bring the CUDA 13.0 runtime, and `--gpus all` brings the driver.
FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

# uv copied from its official image, pinned the same way. No curl | sh installer.
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /bin/uv

# copy: the cache mount below is a different filesystem, so hardlinks can't work.
# compile bytecode: faster first import of torch at container start.
# downloads never: use the image's Python; fail loudly instead of fetching another one.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first. This layer is rebuilt only when pyproject.toml or uv.lock change.
# The uv cache lives in BuildKit's cache, not in the image, and survives between builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked

# Code last. Editing gpu_check.py rebuilds only this small layer.
COPY gpu_check.py .

CMD ["python", "gpu_check.py"]
