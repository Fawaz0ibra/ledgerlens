# LedgerLens

An AI platform that reads supplier invoices, checks them and flags problems, built from scratch and in
public as a production-grade AI/ML engineering project.

The planned pipeline: invoice → layout detection and OCR → a fine-tuned extractor served with vLLM →
data validation → multi-agent review (policy lookup, anomaly checks) → human approval. Everything is
tested against our own synthetic bilingual Arabic/English invoices.

**Status:** repository setup. Nothing here processes invoices yet.

## Layout

| Path | What it holds |
|---|---|
| `src/ledgerlens/contracts/` | The invoice contract (Pydantic models) and its arithmetic and tax checks |
| `scripts/invoice_demo.py` | A runnable tour of the contract: `uv run scripts/invoice_demo.py` |
| `docs/adr/` | Decision records: what we chose, what we rejected, and the numbers behind it |
| `data/README.md` | The data policy and the register of datasets we use |
| `tools/gpu-check/` | Checks that PyTorch can use the GPU, on the host and inside Docker |

## Working on the repo

Secret checks run before every commit. Set them up once per clone:

```bash
uv tool install pre-commit==4.7.0
pre-commit install
```

## Data

Only public datasets with a recorded licence, or synthetic invoices. Never real company documents. See
[data/README.md](data/README.md).

## Licence

[Apache-2.0](LICENSE). The reasons are in [ADR 0002](docs/adr/0002-licence-apache-2.0.md).
