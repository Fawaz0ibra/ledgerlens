"""The ground-truth boxes: one for every printed value, around its text, and where the PDF really has it.

These tests start a real headless Chromium, once for the whole file (the renderer fixture, conftest.py).
"""

import json
from collections import Counter
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest

from ledgerlens_datagen.generate import SyntheticInvoice, generate
from ledgerlens_datagen.layout import GroundTruth
from ledgerlens_datagen.render import PNG_SCALE, POINTS_PER_PX, Renderer

SEED = 20261109
_SAMPLE = list(generate(SEED, 20))
STANDARD = [s for s in _SAMPLE if s.invoice.invoice_type == "standard"][:3]
SIMPLIFIED = [s for s in _SAMPLE if s.invoice.invoice_type == "simplified"][:3]
PAGES = [pytest.param(s, id=f"{s.invoice.invoice_type}-{s.index}") for s in STANDARD + SIMPLIFIED]

# What every page prints: (field, lang), where lang tells apart the two copies of a value printed in both
# languages.
ON_EVERY_PAGE = [
    ("invoice.invoice_type", "ar"),
    ("invoice.invoice_type", "en"),
    ("invoice.seller.name_ar", None),
    ("invoice.seller.name_en", None),
    ("seller_address", "ar"),
    ("seller_address", "en"),
    ("invoice.seller.vat_number", None),
    ("qr_code", None),
    ("invoice.invoice_number", None),
    ("invoice.issue_date", None),
    ("issued_at", None),
    ("invoice.subtotal", None),
    ("invoice.vat_total", None),
    ("invoice.total", None),
    ("invoice.currency", "ar"),
    ("invoice.currency", "en"),
]
# Only a standard invoice names its buyer.
BUYER = [
    ("invoice.buyer.name_ar", None),
    ("invoice.buyer.name_en", None),
    ("buyer_address", "ar"),
    ("buyer_address", "en"),
    ("invoice.buyer.vat_number", "ar"),
    ("invoice.buyer.vat_number", "en"),
]
PER_LINE = [
    "invoice.lines.{n}.description_ar",
    "invoice.lines.{n}.description_en",
    "invoice.lines.{n}.quantity",
    "invoice.lines.{n}.unit_price",
    "invoice.lines.{n}.line_total",
    "invoice.lines.{n}.vat_rate",
    "line_vat.{n}.vat_amount",
    "line_vat.{n}.amount_with_vat",
]


@pytest.fixture(scope="module")
def drawn(renderer: Renderer) -> dict[int, tuple[GroundTruth, bytes]]:
    """Each sample page drawn once: its ground truth and its PDF, by invoice index."""
    pages = {}
    for synthetic in STANDARD + SIMPLIFIED:
        page = renderer.render(synthetic)
        pages[synthetic.index] = (GroundTruth(**dict(synthetic), layout=page.layout), page.pdf)
    return pages


def _value_at(data: Any, path: str) -> Any:
    for key in path.split("."):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def _pdf_characters(pdf: bytes) -> list[tuple[str, float, float]]:
    """Each character in the PDF's text layer and the centre of its box, in points from the page's top-left
    corner. Spaces are left out, and so is the watermark: the only text drawn at an angle."""
    document = pdfium.PdfDocument(pdf)
    try:
        page = document[0]
        height = page.get_height()
        text = page.get_textpage()
        characters = []
        for index in range(text.count_chars()):
            character = text.get_text_range(index, 1)
            if character.isspace() or pdfium_c.FPDFText_GetCharAngle(text.raw, index) != 0:
                continue
            left, bottom, right, top = text.get_charbox(index)
            # A PDF counts from the bottom-left corner, with y growing upwards.
            characters.append((character, (left + right) / 2, height - (bottom + top) / 2))
        return characters
    finally:
        document.close()


@pytest.mark.parametrize("synthetic", PAGES)
def test_every_printed_value_has_exactly_one_box(
    synthetic: SyntheticInvoice, drawn: dict[int, tuple[GroundTruth, bytes]]
) -> None:
    truth, _ = drawn[synthetic.index]
    expected = list(ON_EVERY_PAGE)
    if truth.invoice.buyer is not None:
        expected += BUYER
    for n in range(len(truth.invoice.lines)):
        expected += [(path.format(n=n), None) for path in PER_LINE]
    # Counted, so a value boxed twice fails too.
    assert Counter((box.field, box.lang) for box in truth.layout.fields) == Counter(expected)


@pytest.mark.parametrize("synthetic", PAGES)
def test_each_box_names_a_value_in_the_same_json(
    synthetic: SyntheticInvoice, drawn: dict[int, tuple[GroundTruth, bytes]]
) -> None:
    truth, _ = drawn[synthetic.index]
    data = json.loads(truth.model_dump_json())
    for box in truth.layout.fields:
        assert _value_at(data, box.field) is not None, box.field


def test_each_box_holds_the_value_as_the_page_prints_it(drawn: dict[int, tuple[GroundTruth, bytes]]) -> None:
    truth, _ = drawn[STANDARD[0].index]
    text = {(box.field, box.lang): box.text for box in truth.layout.fields}
    invoice = truth.invoice
    assert invoice.buyer is not None
    assert text["invoice.seller.name_en", None] == invoice.seller.name_en
    assert text["invoice.buyer.vat_number", "en"] == invoice.buyer.vat_number
    assert text["invoice.invoice_type", "en"] == "Tax Invoice"  # the JSON says "standard"
    assert text["invoice.issue_date", None] == invoice.issue_date.strftime("%d/%m/%Y")  # the JSON: yyyy-mm-dd
    assert text["invoice.total", None] == f"{invoice.total:,.2f}"  # with a thousands comma
    assert text["invoice.lines.0.vat_rate", None] == "15%"  # the JSON says "0.15"
    assert text["line_vat.0.vat_amount", None] == f"{truth.line_vat[0].vat_amount:,.2f}"
    assert text["invoice.currency", "ar"] == "ر.س"
    assert text["qr_code", None] is None  # an image


@pytest.mark.parametrize("synthetic", PAGES)
def test_boxes_are_inside_the_page_and_agree_in_both_units(
    synthetic: SyntheticInvoice, drawn: dict[int, tuple[GroundTruth, bytes]]
) -> None:
    truth, _ = drawn[synthetic.index]
    width, height = truth.layout.png_size
    assert (width, height) == (1588, 2246)
    pixels_per_point = PNG_SCALE / POINTS_PER_PX
    for box in truth.layout.fields:
        x0, y0, x1, y1 = box.png
        assert 0 <= x0 < x1 <= width, box
        assert 0 <= y0 < y1 <= height, box
        # Under a pixel apart: the PNG box is rounded outwards to whole pixels, the PDF box to 0.01 point.
        for pixels, points in zip(box.png, box.pdf, strict=True):
            assert abs(pixels - points * pixels_per_point) < 1.02, box


@pytest.mark.parametrize("synthetic", PAGES)
def test_the_pdf_has_each_text_inside_its_box(
    synthetic: SyntheticInvoice, drawn: dict[int, tuple[GroundTruth, bytes]]
) -> None:
    # The boxes come from the screen layout. Printing the PDF lays the page out again, so this checks that
    # the PDF put every text in its box: the characters whose centres fall inside, no more and no fewer.
    # They're compared sorted, because the PDF holds Arabic in the order it's drawn, and pdfium reads some
    # Arabic words back to front (مؤسسة as ةسسؤم).
    truth, pdf = drawn[synthetic.index]
    characters = _pdf_characters(pdf)
    for box in truth.layout.fields:
        if box.text is None:
            continue
        x0, y0, x1, y1 = box.pdf
        inside = [character for character, x, y in characters if x0 <= x <= x1 and y0 <= y <= y1]
        assert sorted(inside) == sorted(c for c in box.text if not c.isspace()), box


def test_the_same_invoice_gives_the_same_boxes(renderer: Renderer) -> None:
    assert renderer.render(SIMPLIFIED[0]).layout == renderer.render(SIMPLIFIED[0]).layout
