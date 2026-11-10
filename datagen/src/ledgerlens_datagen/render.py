"""Draw a synthetic invoice as the page a person would see: HTML from a template, then PDF and PNG from
headless Chromium, and the box around every value on the page.

The page is A4. The browser lays it out at 96 CSS pixels per inch (794 x 1123), the PNG is drawn at twice
that (1588 x 2246) so small print stays sharp, and the PDF comes from the same layout.
"""

import base64
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cache
from importlib.metadata import version
from importlib.resources import files
from math import ceil, floor
from typing import Any

import segno
from jinja2 import Environment, PackageLoader, StrictUndefined
from markupsafe import Markup
from playwright.sync_api import Page, sync_playwright

from ledgerlens_datagen.generate import SyntheticInvoice
from ledgerlens_datagen.layout import FieldBox, Layout
from ledgerlens_datagen.world import Address

# A4 (210 x 297 mm) at 96 CSS pixels per inch, and the PNG drawn at twice that.
PAGE_WIDTH_PX = 794
PAGE_HEIGHT_PX = 1123
PNG_SCALE = 2
# A PDF counts in points, 72 to the inch: 72 / 96 of a CSS pixel.
POINTS_PER_PX = 0.75

# Printed at the top and bottom of every page, with a watermark across the middle, so a page can't pass
# as a real tax invoice even when cropped.
MARKER_AR = "عينة اصطناعية لأغراض الاختبار — ليست فاتورة ضريبية"
MARKER_EN = "SYNTHETIC SAMPLE FOR TESTING — NOT A TAX INVOICE"

# Runs in the page once it is drawn: for every element marked data-field, its text and the box around that
# text, in CSS pixels. The element's own box won't do, because a <div> is as wide as its column however
# short its text. A Range over the element's contents measures the text itself. An image has no text, so
# it keeps its own box.
_MEASURE = """() => [...document.querySelectorAll("[data-field]")].map(element => {
  let box = element.getBoundingClientRect();
  if (element.tagName !== "IMG") {
    const range = document.createRange();
    range.selectNodeContents(element);
    box = range.getBoundingClientRect();
  }
  return {
    field: element.dataset.field,
    lang: element.dataset.lang ?? null,
    text: element.tagName === "IMG" ? null : element.innerText,
    box: [box.left, box.top, box.right, box.bottom],
  };
})"""


@dataclass(frozen=True)
class RenderedPage:
    pdf: bytes
    png: bytes
    layout: Layout


def _money(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _quantity(quantity: Decimal) -> str:
    return f"{quantity:,}"


def _percent(rate: Decimal) -> str:
    return f"{rate * 100:.0f}%"


def _day_month_year(day: date) -> str:
    # ZATCA: a date written in numerals goes day/month/year.
    return day.strftime("%d/%m/%Y")


def _clock(moment: datetime) -> str:
    return moment.strftime("%H:%M:%S")


def _address_ar(address: Address) -> str:
    a = address
    return f"{a.building_number} {a.street_ar}، حي {a.district_ar}، {a.city_ar} {a.postal_code}"


def _address_en(address: Address) -> str:
    a = address
    return f"{a.building_number} {a.street_en}, {a.district_en}, {a.city_en} {a.postal_code}"


# autoescape: every value is HTML-escaped, so a name containing < or & can't break the page.
# StrictUndefined: a misspelt variable in the template is an error, not an empty string.
_ENV = Environment(
    loader=PackageLoader("ledgerlens_datagen"),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_ENV.filters.update(money=_money, quantity=_quantity, percent=_percent, day_month_year=_day_month_year, clock=_clock)
_ENV.globals.update(address_ar=_address_ar, address_en=_address_en)


@cache
def _font_css() -> Markup:
    """@font-face rules with the bundled font files inside them: the page loads nothing from disk or network."""
    faces = []
    for weight, name in ((400, "IBMPlexSansArabic-Regular.ttf"), (700, "IBMPlexSansArabic-Bold.ttf")):
        data = base64.b64encode(files("ledgerlens_datagen").joinpath("fonts", name).read_bytes()).decode("ascii")
        faces.append(
            f'@font-face {{ font-family: "Plex Arabic"; font-weight: {weight}; '
            f'src: url(data:font/ttf;base64,{data}) format("truetype"); }}'
        )
    return Markup("\n".join(faces))


def render_html(synthetic: SyntheticInvoice) -> str:
    invoice = synthetic.invoice
    rows = list(zip(invoice.lines, synthetic.line_vat, strict=True))
    return _ENV.get_template("invoice.html.j2").render(
        s=synthetic,
        invoice=invoice,
        seller=invoice.seller,
        buyer=invoice.buyer,
        standard=invoice.invoice_type == "standard",
        rows=rows,
        qr_image=segno.make(synthetic.qr_code, error="m").svg_data_uri(),
        marker_ar=MARKER_AR,
        marker_en=MARKER_EN,
        font_css=_font_css(),
    )


def _field_box(measured: dict[str, Any]) -> FieldBox:
    """One measurement from the browser, in CSS pixels, as a box in PNG pixels and in PDF points."""
    x0, y0, x1, y1 = measured["box"]
    s = PNG_SCALE
    p = POINTS_PER_PX
    return FieldBox(
        field=measured["field"],
        lang=measured["lang"],
        text=measured["text"],
        png=(floor(x0 * s), floor(y0 * s), ceil(x1 * s), ceil(y1 * s)),
        pdf=(round(x0 * p, 2), round(y0 * p, 2), round(x1 * p, 2), round(y1 * p, 2)),
    )


class Renderer:
    """Draws every page in one browser tab that stays open: starting Chromium takes far longer than a page."""

    def __init__(self, page: Page, engine: str) -> None:
        self._page = page
        self.engine = engine  # which browser drew the pages, for the dataset's record

    def render(self, synthetic: SyntheticInvoice) -> RenderedPage:
        return self.draw(render_html(synthetic))

    def draw(self, html: str) -> RenderedPage:
        page = self._page
        page.set_content(html, wait_until="load")
        # Wait for the fonts, then stop if one failed. Otherwise Chromium would quietly draw the page in a
        # fallback font, and the dataset would no longer be what the dataset card says.
        failed = page.evaluate(
            "document.fonts.ready.then(fonts => [...fonts].filter(f => f.status === 'error').map(f => f.weight))"
        )
        if failed:
            raise RuntimeError(f"bundled fonts failed to load (weights {failed})")
        png = page.screenshot(type="png")
        # Measured from the layout the screenshot was just taken of. Printing the PDF lays the page out
        # again; the tests check that the PDF's text sits in these same boxes.
        fields = tuple(_field_box(measured) for measured in page.evaluate(_MEASURE))
        pdf = page.pdf(width="210mm", height="297mm", print_background=True, prefer_css_page_size=True)
        layout = Layout(png_size=(PAGE_WIDTH_PX * PNG_SCALE, PAGE_HEIGHT_PX * PNG_SCALE), fields=fields)
        return RenderedPage(pdf=pdf, png=png, layout=layout)


@contextmanager
def open_renderer() -> Iterator[Renderer]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": PAGE_WIDTH_PX, "height": PAGE_HEIGHT_PX}, device_scale_factor=PNG_SCALE
        )
        # Make the PDF from the screen layout too, so the PDF and the PNG are one layout.
        page.emulate_media(media="screen")
        yield Renderer(page, engine=f"Chromium {browser.version} through Playwright {version('playwright')}")
