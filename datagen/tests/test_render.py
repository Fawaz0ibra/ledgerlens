"""Drawing invoices: one A4 page with the marker, in the bundled fonts, and the same pixels every time.

These tests start a real headless Chromium, once for the whole file (the renderer fixture, conftest.py).
"""

import struct

import pypdfium2 as pdfium
import pytest
from markupsafe import Markup

from ledgerlens_datagen import render
from ledgerlens_datagen.generate import SyntheticInvoice, generate
from ledgerlens_datagen.render import MARKER_AR, MARKER_EN, Renderer, render_html

SEED = 20261109
_SAMPLE = list(generate(SEED, 20))
STANDARD = next(s for s in _SAMPLE if s.invoice.invoice_type == "standard")
SIMPLIFIED = next(s for s in _SAMPLE if s.invoice.invoice_type == "simplified")


def _pdf_text_and_size(pdf: bytes) -> tuple[int, str, tuple[float, float]]:
    document = pdfium.PdfDocument(pdf)
    try:
        page = document[0]
        text = page.get_textpage().get_text_range()
        return len(document), text, page.get_size()
    finally:
        document.close()


@pytest.mark.parametrize(
    ("synthetic", "title_ar", "title_en"),
    [
        pytest.param(STANDARD, "فاتورة ضريبية", "Tax Invoice", id="standard"),
        pytest.param(SIMPLIFIED, "فاتورة ضريبية مبسطة", "Simplified Tax Invoice", id="simplified"),
    ],
)
def test_the_html_has_the_title_the_marker_and_the_values(
    synthetic: SyntheticInvoice, title_ar: str, title_en: str
) -> None:
    html = render_html(synthetic)
    invoice = synthetic.invoice
    assert invoice.seller.name_ar is not None
    for text in (title_ar, title_en, MARKER_AR, MARKER_EN, invoice.invoice_number, invoice.seller.name_ar):
        assert text in html
    assert f"{invoice.total:,.2f}" in html
    assert invoice.issue_date.strftime("%d/%m/%Y") in html
    # Only a standard invoice has a buyer block.
    assert ('data-field="invoice.buyer.name_ar"' in html) == (invoice.buyer is not None)


def test_text_is_escaped_so_a_name_cant_break_the_page() -> None:
    seller = STANDARD.invoice.seller.model_copy(update={"name_en": "<b>Bold</b> & Co."})
    synthetic = STANDARD.model_copy(update={"invoice": STANDARD.invoice.model_copy(update={"seller": seller})})
    html = render_html(synthetic)
    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; Co." in html
    assert "<b>Bold</b>" not in html


def test_the_png_is_one_a4_page_at_twice_96_pixels_per_inch(renderer: Renderer) -> None:
    png = renderer.render(STANDARD).png
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])  # from the PNG header
    assert (width, height) == (1588, 2246)


def test_the_pdf_is_one_a4_page_with_the_marker_and_the_values(renderer: Renderer) -> None:
    pages, text, (width, height) = _pdf_text_and_size(renderer.render(STANDARD).pdf)
    assert pages == 1
    assert (round(width), round(height)) == (595, 842)  # A4 in points, 72 per inch
    for value in (MARKER_EN, STANDARD.invoice.invoice_number, f"{STANDARD.invoice.total:,.2f}"):
        assert value in text


def test_the_same_invoice_gives_the_same_pixels(renderer: Renderer) -> None:
    assert renderer.render(SIMPLIFIED).png == renderer.render(SIMPLIFIED).png


def test_a_font_that_fails_to_load_stops_the_render(renderer: Renderer, monkeypatch: pytest.MonkeyPatch) -> None:
    # Four bytes of zeros where the font file should be.
    broken = '@font-face { font-family: "Plex Arabic"; src: url(data:font/ttf;base64,AAAA) format("truetype"); }'
    monkeypatch.setattr(render, "_font_css", lambda: Markup(broken))
    with pytest.raises(RuntimeError, match="bundled fonts failed to load"):
        renderer.render(STANDARD)
