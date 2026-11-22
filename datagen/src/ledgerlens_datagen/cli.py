"""The command line: print synthetic invoices as JSON, one per line, or draw them to files.

Examples:
uv run ledgerlens-datagen --seed 7 --count 3
uv run ledgerlens-datagen --seed 7 --count 3 --out data/samples
uv run ledgerlens-datagen --seed 7 --count 500 --anomaly-rate 0.5 --anomalies price_above_agreed --out data/eval-price
uv run ledgerlens-datagen --seed 7 --count 2000 --drift-from 2026-07-01 --out data/drift
"""

import argparse
import json
from collections.abc import Sequence
from datetime import date
from importlib.metadata import version
from pathlib import Path

from pydantic import TypeAdapter

from ledgerlens_datagen.anomalies import DEFAULT_RATE, Settings, labelled_invoice
from ledgerlens_datagen.labels import ANOMALY_TYPES
from ledgerlens_datagen.layout import GroundTruth
from ledgerlens_datagen.purchasing import PurchaseOrder, build_purchasing
from ledgerlens_datagen.render import open_renderer
from ledgerlens_datagen.world import build_world

ORDERS = TypeAdapter(list[PurchaseOrder])


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ledgerlens-datagen", description="Make synthetic invoices.")
    # Required on purpose: there is no hidden default randomness, so every output can be made again.
    parser.add_argument("--seed", type=int, required=True, help="the same seed always gives the same invoices")
    parser.add_argument("--count", type=int, default=1, help="how many invoices (default 1)")
    parser.add_argument(
        "--anomaly-rate",
        type=float,
        default=DEFAULT_RATE,
        help=f"the share of invoices with a labelled anomaly (default {DEFAULT_RATE})",
    )
    parser.add_argument(
        "--anomalies", nargs="+", choices=ANOMALY_TYPES, default=ANOMALY_TYPES, help="only these anomalies"
    )
    parser.add_argument(
        "--drift-from",
        type=date.fromisoformat,
        help="from this issue date (YYYY-MM-DD), some vendors switch to a new page design and anomalies come "
        "twice as often",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write NNNNN.png, .pdf and .json (the ground truth) for each invoice into this folder, with the "
        "buyers' records, instead",
    )
    args = parser.parse_args(argv)

    settings = Settings(anomaly_rate=args.anomaly_rate, types=tuple(args.anomalies), drift_from=args.drift_from)
    world = build_world(args.seed)
    purchasing = build_purchasing(args.seed, world)
    invoices = (labelled_invoice(world, purchasing, args.seed, index, settings) for index in range(args.count))
    if args.out is None:
        for synthetic in invoices:
            print(synthetic.model_dump_json())
        return

    args.out.mkdir(parents=True, exist_ok=True)
    # A duplicate bills the same order again, so each order is kept once, keyed by its buyer and number.
    orders: dict[tuple[str, str], PurchaseOrder] = {}
    with open_renderer() as renderer:
        for synthetic in invoices:
            page = renderer.render(synthetic)
            truth = GroundTruth(**dict(synthetic), layout=page.layout)
            stem = args.out / f"{synthetic.index:05d}"
            stem.with_suffix(".json").write_text(truth.model_dump_json(indent=2) + "\n", encoding="utf-8")
            stem.with_suffix(".pdf").write_bytes(page.pdf)
            stem.with_suffix(".png").write_bytes(page.png)
            if (order := synthetic.purchase_order) is not None:
                orders.setdefault((order.buyer_vat_number, order.order_number), order)
        # What made these files (ADR 0006). Two runs with the same record write the same JSON and PNG files;
        # only the PDFs differ, because each records when it was made. No date here, for the same reason.
        record = {
            "generator": f"ledgerlens-datagen {version('ledgerlens-datagen')}",
            "renderer": renderer.engine,
            "seed": args.seed,
            "count": args.count,
            "settings": settings.model_dump(mode="json"),
        }
    # What a buyer checks an invoice against: the companies, each one's vendor master and agreed prices, and
    # the orders the invoices bill.
    (args.out / "world.json").write_text(world.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (args.out / "purchasing.json").write_text(purchasing.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (args.out / "purchase_orders.json").write_bytes(ORDERS.dump_json(list(orders.values()), indent=2) + b"\n")
    (args.out / "dataset.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.count} invoices to {args.out}")
