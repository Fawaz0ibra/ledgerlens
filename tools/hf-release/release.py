"""Turn a folder the generator wrote into a Hugging Face dataset release (ADR 0009): Parquet files holding each
page's image and ground truth, the buyers' records, and a dataset card. Nothing is uploaded here; the
folder it writes is what gets reviewed, then uploaded with `hf upload`.

    uv run --group release python tools/hf-release/release.py data/release-0.3.0 data/hf-0.3.0 --repo USER/NAME

The splits follow time, as production data does: train and validation come before the drift date, and
test after it. A model learns from the past and is tested on a future that has drifted.
"""

import argparse
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from datasets import Dataset, Features, Image, List, Value

REPO_URL = "https://github.com/Fawaz0ibra/ledgerlens"
# Train is January to April, validation May and June; test starts where drift does.
VALIDATION_FROM = date(2026, 5, 1)
RECORDS = ("world.json", "purchasing.json", "purchase_orders.json", "dataset.json")

FEATURES = Features(
    {
        "image": Image(),
        "index": Value("int32"),
        "invoice_type": Value("string"),
        "issue_date": Value("string"),
        "design": Value("string"),
        "anomaly_type": Value("string"),  # null for a clean invoice
        "anomaly_fields": List(Value("string")),
        "duplicate_of": Value("int32"),
        "ground_truth": Value("string"),  # the page's whole JSON file, exactly as the generator wrote it
    }
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="a folder written by ledgerlens-datagen --out")
    parser.add_argument("out", type=Path, help="where to write the release (emptied first)")
    parser.add_argument("--repo", required=True, help="the Hub dataset it will be uploaded to, USER/NAME")
    args = parser.parse_args()

    record = json.loads((args.folder / "dataset.json").read_text(encoding="utf-8"))
    drift_from = record["settings"]["drift_from"]
    if drift_from is None:
        raise SystemExit("a release needs drift (--drift-from): its test split starts on the drift date")
    rows = [_row(path) for path in sorted(args.folder.glob("[0-9]*.json"))]
    splits = {
        name: [r for r in rows if _split(r["issue_date"], drift_from) == name]
        for name in ("train", "validation", "test")
    }

    if args.out.exists():
        shutil.rmtree(args.out)
    (args.out / "data").mkdir(parents=True)
    for name, split_rows in splits.items():
        Dataset.from_list(split_rows, features=FEATURES).to_parquet(
            args.out / "data" / f"{name}-00000-of-00001.parquet"
        )
    (args.out / "records").mkdir()
    for name in RECORDS:
        shutil.copy2(args.folder / name, args.out / "records" / name)
    (args.out / "README.md").write_text(_card(record, splits, args.repo), encoding="utf-8")
    for name, split_rows in splits.items():
        print(f"{name}: {len(split_rows)} invoices")
    print(f"wrote {args.out}")


def _row(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    truth = json.loads(text)
    anomaly = truth["anomaly"] or {}
    return {
        "image": {"bytes": path.with_suffix(".png").read_bytes(), "path": path.with_suffix(".png").name},
        "index": truth["index"],
        "invoice_type": truth["invoice"]["invoice_type"],
        "issue_date": truth["invoice"]["issue_date"],
        "design": truth["design"],
        "anomaly_type": anomaly.get("type"),
        "anomaly_fields": anomaly.get("fields", []),
        "duplicate_of": anomaly.get("duplicate_of"),
        "ground_truth": text,
    }


def _split(issue_date: str, drift_from: str) -> str:
    if issue_date >= drift_from:  # ISO dates compare correctly as text
        return "test"
    return "validation" if issue_date >= VALIDATION_FROM.isoformat() else "train"


def _card(record: dict[str, Any], splits: dict[str, list[dict[str, Any]]], repo: str) -> str:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    version = record["generator"].split()[-1]
    settings = record["settings"]
    index_split = {r["index"]: name for name, rows in splits.items() for r in rows}
    duplicates = [(name, r) for name, rows in splits.items() for r in rows if r["duplicate_of"] is not None]
    crossing = sum(index_split[r["duplicate_of"]] != name for name, r in duplicates)
    table = "\n".join(
        f"| {name} | {_period(name, settings['drift_from'])} | {len(rows)} | "
        f"{sum(r['anomaly_type'] is not None for r in rows)} | {sum(r['design'] == 'b' for r in rows)} |"
        for name, rows in splits.items()
    )
    types = Counter(r["anomaly_type"] for rows in splits.values() for r in rows if r["anomaly_type"])
    header = f"""---
license: apache-2.0
language:
- ar
- en
pretty_name: LedgerLens synthetic invoices
size_categories:
- 1K<n<10K
task_categories:
- object-detection
- image-to-text
tags:
- synthetic
- invoices
- document-ai
- arabic
- zatca
- anomaly-detection
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*.parquet
  - split: validation
    path: data/validation-*.parquet
  - split: test
    path: data/test-*.parquet
---

# LedgerLens synthetic invoices, release v{version}

Made by `{record["generator"]}` (drawn by {record["renderer"]}) at commit
[`{commit[:7]}`]({REPO_URL}/tree/{commit}) with:

```bash
uv run ledgerlens-datagen --seed {record["seed"]} --count {record["count"]} --drift-from {settings["drift_from"]}
```

The same command at that commit writes the same JSON and PNG files. Anomaly rate {settings["anomaly_rate"]}.

| Split | Issued | Invoices | With an anomaly | In design b |
|---|---|---|---|---|
{table}

Anomalies by type: {", ".join(f"{kind} {n}" for kind, n in sorted(types.items()))}. Of the {len(duplicates)}
duplicates, {crossing} repeat an invoice from an earlier split; a duplicate detector sees the history before it.

```python
import json
from datasets import load_dataset

invoices = load_dataset("{repo}", revision="v{version}")
truth = json.loads(invoices["test"][0]["ground_truth"])  # values, boxes, anomaly label, purchase order
```

Each row holds the page (`image`), a few columns to filter on, and `ground_truth`: the page's whole JSON
file. `records/` holds the buyers' records the anomalies are checked against and the generator's
`dataset.json`. The PDFs aren't included: each records when it was made, so they differ on every run. The
command above makes them.

"""
    card = (Path(__file__).parents[2] / "datagen" / "DATASET_CARD.md").read_text(encoding="utf-8")
    card = card.replace(" (this folder)", "")
    # The card's links are relative to datagen/ in the repo; on the Hub they point at the release's commit.
    card = re.sub(r"\]\(\.\./", f"]({REPO_URL}/blob/{commit}/", card)
    card = re.sub(r"\]\((?!https?://)", f"]({REPO_URL}/blob/{commit}/datagen/", card)
    return header + card


def _period(name: str, drift_from: str) -> str:
    return {
        "train": f"before {VALIDATION_FROM.isoformat()}",
        "validation": f"{VALIDATION_FROM.isoformat()} to {drift_from}",
        "test": f"from {drift_from} (drift)",
    }[name]


if __name__ == "__main__":
    main()
