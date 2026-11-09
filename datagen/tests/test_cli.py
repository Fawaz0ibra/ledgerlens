"""The command that draws invoices to files.

It has its own file because it starts its own browser. Playwright's synchronous API allows one running
session per process, and test_render.py keeps one open for all of its tests; pytest closes it when that
file's tests are done.
"""

from pathlib import Path

import pytest

from ledgerlens_datagen.cli import main
from ledgerlens_datagen.generate import SyntheticInvoice, generate

SEED = 20261109


def test_the_command_writes_json_pdf_and_png_for_each_invoice(
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
    ]
    # The JSON next to each page reads back as exactly the invoice the generator made.
    expected = list(generate(SEED, 2))[1]
    assert SyntheticInvoice.model_validate_json((tmp_path / "00001.json").read_text(encoding="utf-8")) == expected
    assert capsys.readouterr().out == f"wrote 2 invoices to {tmp_path}\n"
