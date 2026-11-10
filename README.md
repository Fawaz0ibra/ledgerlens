# LedgerLens

[![CI](https://github.com/Fawaz0ibra/ledgerlens/actions/workflows/ci.yml/badge.svg)](https://github.com/Fawaz0ibra/ledgerlens/actions/workflows/ci.yml)

An AI platform that reads supplier invoices, checks them and flags problems, built from scratch and in
public as a production-grade AI/ML engineering project.

The planned pipeline: invoice → layout detection and OCR → a fine-tuned extractor served with vLLM →
data validation → multi-agent review (policy lookup, anomaly checks) → human approval. Everything is
tested against our own synthetic bilingual Arabic/English invoices.

**Status:** the invoice contract and an HTTP API that checks invoices sent as JSON, with tests, shipped
as a container image and run next to Postgres with docker compose; CI checks every change. A generator
makes synthetic invoice pages with their ground truth: every value, its text as printed, and its box on
the page. Nothing reads invoice images yet.

## Layout

| Path | What it holds |
|---|---|
| `src/ledgerlens/contracts/` | The invoice contract (Pydantic models) and its arithmetic and tax checks |
| `src/ledgerlens/api/` | The HTTP service: settings, JSON logs, health checks, error responses, the invoice check |
| `tests/` | pytest tests for the contract, the checks and the API; shared fixtures are in `conftest.py` |
| `datagen/` | The synthetic invoice generator, a separate package in the same uv workspace: `uv run ledgerlens-datagen --seed 7` |
| `Dockerfile`, `.dockerignore` | The API image, built in two stages ([ADR 0004](docs/adr/0004-container-image-two-stages-on-slim.md)) |
| `compose.yaml` | The API and its Postgres database on one machine |
| `.github/workflows/ci.yml` | CI: lint, format, types and tests, then the image build and a smoke test |
| `scripts/invoice_demo.py` | A runnable tour of the contract: `uv run scripts/invoice_demo.py` |
| `scripts/api_demo.py` | Sends example requests to a running API: `uv run scripts/api_demo.py` |
| `scripts/sample_invoice.json` | The synthetic sample invoice both demos use |
| `docs/adr/` | Decision records: what we chose, what we rejected, and the numbers behind it |
| `data/README.md` | The data policy and the register of datasets we use |
| `tools/gpu-check/` | Checks that PyTorch can use the GPU, on the host and inside Docker |
| `tools/render-compare/` | The measurement behind ADR 0006: two renderers drawing the same invoice pages |
| `tools/box-overlay/` | Draws the ground-truth boxes over generated pages, to check them by eye |

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

## Synthetic invoices

The generator in `datagen/` makes seeded bilingual Arabic/English invoices in the style ZATCA (the Saudi tax
authority) requires, with a visible synthetic-sample marker and test-only VAT numbers. It draws the pages
with headless Chromium, which needs a one-time setup:

```bash
uv run playwright install --with-deps --only-shell chromium     # the browser and the Linux libraries it loads (asks for sudo)
uv run ledgerlens-datagen --seed 7 --count 3                    # JSON, one invoice per line
uv run ledgerlens-datagen --seed 7 --count 3 --out data/samples # PNG, PDF and ground-truth JSON per invoice (data/ is git-ignored)
uv run python tools/box-overlay/overlay.py data/samples         # the boxes drawn over each page, in data/samples/boxes/
```

What each file holds, the ZATCA rules followed, the test VAT numbers and the limits are in the
[dataset card](datagen/DATASET_CARD.md).

## Checks

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs these four on every pull request and every
push to `main`, then builds the image and starts it. Run them before pushing:

```bash
uv run ruff check .    # lint: likely bugs and needlessly awkward code (--fix applies ruff's safe fixes)
uv run ruff format .   # one layout for all the code (--check only reports)
uv run mypy            # type hints, in strict mode
uv run pytest --cov    # every test, failing unless every line and branch ran
```

Docker must be running: the API tests start a throwaway Postgres in a container (testcontainers) and
remove it at the end. The generator's tests draw real pages, so they need the browser setup above. Any warning fails the test run (`filterwarnings = ["error"]` in `pyproject.toml`),
so a deprecation is dealt with when it first appears.

## Data

Only public datasets with a recorded licence, or synthetic invoices. Never real company documents. See
[data/README.md](data/README.md).

## Licence

[Apache-2.0](LICENSE). The reasons are in [ADR 0002](docs/adr/0002-licence-apache-2.0.md).
