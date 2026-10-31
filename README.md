# LedgerLens

An AI platform that reads supplier invoices, checks them and flags problems, built from scratch and in
public as a production-grade AI/ML engineering project.

The planned pipeline: invoice → layout detection and OCR → a fine-tuned extractor served with vLLM →
data validation → multi-agent review (policy lookup, anomaly checks) → human approval. Everything is
tested against our own synthetic bilingual Arabic/English invoices.

**Status:** the invoice contract and an HTTP API that checks invoices sent as JSON. Nothing reads
invoice images yet.

## Layout

| Path | What it holds |
|---|---|
| `src/ledgerlens/contracts/` | The invoice contract (Pydantic models) and its arithmetic and tax checks |
| `src/ledgerlens/api/` | The HTTP service: settings, JSON logs, health checks, error responses, the invoice check |
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

```bash
uv run uvicorn ledgerlens.api.app:create_app --factory
```

Interactive docs are at http://127.0.0.1:8000/docs. Settings come from `LEDGERLENS_*` environment
variables or a git-ignored `.env` file; [.env.example](.env.example) lists them.

## Data

Only public datasets with a recorded licence, or synthetic invoices. Never real company documents. See
[data/README.md](data/README.md).

## Licence

[Apache-2.0](LICENSE). The reasons are in [ADR 0002](docs/adr/0002-licence-apache-2.0.md).
