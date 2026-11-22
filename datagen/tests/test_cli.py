"""The command that draws invoices to files.

It has its own file because it starts its own browser. Playwright's synchronous API allows one running
session per process, and the test files that use the renderer fixture keep one open each; pytest closes it
when that file's tests are done.
"""

import json
from datetime import date
from importlib.metadata import version
from pathlib import Path

import pytest

from ledgerlens_datagen.anomalies import Settings, generate_labelled
from ledgerlens_datagen.cli import ORDERS, main
from ledgerlens_datagen.layout import GroundTruth
from ledgerlens_datagen.purchasing import Purchasing, build_purchasing
from ledgerlens_datagen.world import World, build_world

SEED = 20261109


def test_the_command_writes_the_page_and_its_ground_truth_for_each_invoice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(
        ["--seed", str(SEED), "--count", "3", "--out", str(tmp_path), "--anomaly-rate", "0.5"]
        + ["--anomalies", "total_inflated", "qr_mismatch", "--drift-from", "2026-01-01"]
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "00000.json",
        "00000.pdf",
        "00000.png",
        "00001.json",
        "00001.pdf",
        "00001.png",
        "00002.json",
        "00002.pdf",
        "00002.png",
        "dataset.json",
        "purchase_orders.json",
        "purchasing.json",
        "world.json",
    ]
    # The JSON next to each page reads back as exactly the invoice the generator made, plus its boxes.
    settings = Settings(anomaly_rate=0.5, types=("total_inflated", "qr_mismatch"), drift_from=date(2026, 1, 1))
    generated = list(generate_labelled(SEED, 3, settings))
    truth = GroundTruth.model_validate_json((tmp_path / "00001.json").read_text(encoding="utf-8"))
    assert truth.model_dump(exclude={"layout"}) == generated[1].model_dump()
    assert truth.layout.fields

    # The buyers' records read back too, and hold the order of every standard invoice.
    world = build_world(SEED)
    assert World.model_validate_json((tmp_path / "world.json").read_text(encoding="utf-8")) == world
    purchasing = Purchasing.model_validate_json((tmp_path / "purchasing.json").read_text(encoding="utf-8"))
    assert purchasing == build_purchasing(SEED, world)
    orders = ORDERS.validate_json((tmp_path / "purchase_orders.json").read_bytes())
    assert orders == [s.purchase_order for s in generated if s.purchase_order is not None]
    assert orders

    record = json.loads((tmp_path / "dataset.json").read_text(encoding="utf-8"))
    assert record["generator"] == f"ledgerlens-datagen {version('ledgerlens-datagen')}"
    assert record["renderer"].startswith("Chromium ")
    assert (record["seed"], record["count"]) == (SEED, 3)
    assert Settings.model_validate(record["settings"]) == settings
    assert capsys.readouterr().out == f"wrote 3 invoices to {tmp_path}\n"
