"""The ground truth written next to each page: the invoice (what the page says) and its layout (where).

Module 4 trains vision models on these pages: given the PNG, find each value and read it. A box is
(x0, y0, x1, y1): its left, top, right and bottom edges, measured from the page's top-left corner with y
growing downwards, the way images count. Each box is given twice, in PNG pixels and in PDF points.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ledgerlens_datagen.generate import SyntheticInvoice


class FieldBox(BaseModel):
    """One value printed on the page, and the box around its text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The value's path in this same JSON file: "invoice.lines.0.unit_price", "seller_address".
    field: str
    # Which copy, for a value the page prints in both languages (an address, the title); otherwise None.
    lang: Literal["ar", "en"] | None
    # The text as printed: "1,250.00" where the JSON says "1250.00". None for an image (the QR code).
    text: str | None
    # Rounded outwards, so the left and top edges round down and the right and bottom edges round up.
    png: tuple[int, int, int, int]
    # Points are 1/72 inch, to the hundredth.
    pdf: tuple[float, float, float, float]


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    png_size: tuple[int, int]  # width and height in pixels
    fields: tuple[FieldBox, ...]


class GroundTruth(SyntheticInvoice):
    """The synthetic invoice, plus where each of its values landed on the page."""

    layout: Layout
