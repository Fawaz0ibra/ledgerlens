# LedgerLens

An AI platform that reads supplier invoices, checks them and flags problems, built from scratch and in
public as a production-grade AI/ML engineering project.

The planned pipeline: invoice → layout detection and OCR → a fine-tuned extractor served with vLLM →
data validation → multi-agent review (policy lookup, anomaly checks) → human approval. Everything is
tested against our own synthetic bilingual Arabic/English invoices.

**Status:** the invoice contract and an HTTP API that checks invoices sent as JSON, with tests, shipped
as a container image and run next to Postgres with docker compose. Nothing reads invoice images yet.

## Layout

| Path | What it holds |
|---|---|
| `src/ledgerlens/contracts/` | The invoice contract (Pydantic models) and its arithmetic and tax checks |
| `src/ledgerlens/api/` | The HTTP service: settings, JSON logs, health checks, error responses, the invoice check |
| `tests/` | pytest tests for the contract, the checks and the API; shared fixtures are in `conftest.py` |
| `Dockerfile`, `.dockerignore` | The API image, built in two stages ([ADR 0004](docs/adr/0004-container-image-two-stages-on-slim.md)) |
| `compose.yaml` | The API and its Postgres database on one machine |
| `scripts/invoice_demo.py` | A runnable tour of the contract: `uv run scripts/invoice_demo.py` |
| `scripts/api_demo.py` | Sends example requests to a running API: `uv run scripts/api_demo.py` |
| `scripts/sample_invoice.json` | The synthetic sample invoice both demos use |
| `docs/adr/` | Decision records: what we chose, what we rejected, and the numbers behind it |
| `data/README.md` | The data policy and the register of datasets we use |
| `tools/gpu-check/` | Checks that PyTorch can use the GPU, on the host and inside Docker |

## Working on the repo

Secret checks run before every commit. Set them up once per clone:

```bash
uv tool install pre-commit==4.7.0
pre-commit install
```

## Running the API

The API needs Postgres. Compose runs both; it reads the database password from a git-ignored `.env`:

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" >> .env   # once
docker compose up -d --build
curl localhost:8000/health/ready                           # {"status":"ready"} once Postgres answers
docker compose down                                        # the database volume stays
```

Interactive docs are at http://127.0.0.1:8000/docs. Settings come from `LEDGERLENS_*` environment
variables or the `.env` file; [.env.example](.env.example) lists them. To run the service outside
compose (`uv run uvicorn ledgerlens.api.app:create_app --factory`), set `LEDGERLENS_DATABASE_URL`.

## Running the tests

Docker must be running: the API tests start a throwaway Postgres in a container (testcontainers) and
remove it at the end.

```bash
uv run pytest          # every test
uv run pytest --cov    # the same, plus coverage: fails unless every line and branch ran
```

Any warning fails the run (`filterwarnings = ["error"]` in `pyproject.toml`), so a deprecation is
dealt with when it first appears.

## Data

Only public datasets with a recorded licence, or synthetic invoices. Never real company documents. See
[data/README.md](data/README.md).

## Licence

[Apache-2.0](LICENSE). The reasons are in [ADR 0002](docs/adr/0002-licence-apache-2.0.md).
