"""The command line: print synthetic invoices as JSON, one per line, or draw them to files.

Examples:
uv run ledgerlens-datagen --seed 7 --count 3
uv run ledgerlens-datagen --seed 7 --count 3 --out data/samples
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from ledgerlens_datagen.generate import generate
from ledgerlens_datagen.render import open_renderer


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ledgerlens-datagen", description="Make synthetic invoices.")
    # Required on purpose: there is no hidden default randomness, so every output can be made again.
    parser.add_argument("--seed", type=int, required=True, help="the same seed always gives the same invoices")
    parser.add_argument("--count", type=int, default=1, help="how many invoices (default 1)")
    parser.add_argument(
        "--out", type=Path, help="write NNNNN.json, .pdf and .png for each invoice into this folder, instead"
    )
    args = parser.parse_args(argv)

    invoices = generate(args.seed, args.count)
    if args.out is None:
        for synthetic in invoices:
            print(synthetic.model_dump_json())
        return

    args.out.mkdir(parents=True, exist_ok=True)
    with open_renderer() as renderer:
        for synthetic in invoices:
            page = renderer.render(synthetic)
            stem = args.out / f"{synthetic.index:05d}"
            stem.with_suffix(".json").write_text(synthetic.model_dump_json(indent=2) + "\n", encoding="utf-8")
            stem.with_suffix(".pdf").write_bytes(page.pdf)
            stem.with_suffix(".png").write_bytes(page.png)
    print(f"wrote {args.count} invoices to {args.out}")
