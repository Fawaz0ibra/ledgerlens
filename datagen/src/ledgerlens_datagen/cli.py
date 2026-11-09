"""The command line: print synthetic invoices as JSON, one invoice per line.

Example: uv run ledgerlens-datagen --seed 7 --count 3
"""

import argparse
from collections.abc import Sequence

from ledgerlens_datagen.generate import generate


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ledgerlens-datagen", description="Print synthetic invoices as JSON lines.")
    # Required on purpose: there is no hidden default randomness, so every output can be made again.
    parser.add_argument("--seed", type=int, required=True, help="the same seed always gives the same invoices")
    parser.add_argument("--count", type=int, default=1, help="how many invoices (default 1)")
    args = parser.parse_args(argv)
    for synthetic in generate(args.seed, args.count):
        print(synthetic.model_dump_json())
