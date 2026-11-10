"""The command that draws invoices to files.

It has its own file because it starts its own browser. Playwright's synchronous API allows one running
session per process, and the test files that use the renderer fixture keep one open each; pytest closes it
when that file's tests are done.
"""

import json
from importlib.metadata import version
from pathlib import Path

import pytest

from ledgerlens_datagen.cli import main
from ledgerlens_datagen.generate import generate
from ledgerlens_datagen.layout import GroundTruth

SEED = 20261109


def test_the_command_writes_the_page_and_its_ground_truth_for_each_invoice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["--seed", str(SEED), "--count", "2", "--out", str(tmp_path)])
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "00000.json",
        "00000.pdf",
        "00000.png",
        "00001.json",
        "00001.pdf",
        "00001.png",
        "dataset.json",
    ]
    # The JSON next to each page reads back as exactly the invoice the generator made, plus its boxes.
    expected = list(generate(SEED, 2))[1]
    truth = GroundTruth.model_validate_json((tmp_path / "00001.json").read_text(encoding="utf-8"))
    assert truth.model_dump(exclude={"layout"}) == expected.model_dump()
    assert truth.layout.fields

    record = json.loads((tmp_path / "dataset.json").read_text(encoding="utf-8"))
    assert record["generator"] == f"ledgerlens-datagen {version('ledgerlens-datagen')}"
    assert record["renderer"].startswith("Chromium ")
    assert (record["seed"], record["count"]) == (SEED, 2)
    assert capsys.readouterr().out == f"wrote 2 invoices to {tmp_path}\n"
