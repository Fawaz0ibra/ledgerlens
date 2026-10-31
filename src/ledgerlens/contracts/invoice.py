"""The invoice contract: the one definition of an invoice that every part of LedgerLens shares.

The models check *shape*: types, formats, required fields. They don't check whether the numbers add
up. An invoice with a wrong VAT amount is exactly what LedgerLens exists to catch, so it must still
parse and reach the checks in `checks.py`, instead of being rejected at the door.

Amounts are what the invoice *states*, not what we calculate.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

# Arabic-Indic (٠-٩) and Eastern Arabic-Indic (۰-۹) digits, as printed on Arabic invoices.
_ASCII_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _normalise_vat_number(value: object) -> object:
    """Accept '٣٩٩ ٩٩٩...' or '399-999...' as printed, and store plain ASCII digits."""
    if isinstance(value, str):
        return value.translate(_ASCII_DIGITS).replace(" ", "").replace("-", "")
    return value


# Money is Decimal, never float: invoices must add up to the exact halala (1/100 SAR).
Money = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
VatRate = Annotated[Decimal, Field(ge=0, le=1, decimal_places=4)]  # 0.15 means 15%

# Saudi VAT registration number: 15 digits, starting and ending with 3.
# The before-validator runs first (it is listed last), so Arabic digits are converted before the check.
VatNumber = Annotated[str, StringConstraints(pattern=r"^3[0-9]{13}3$"), BeforeValidator(_normalise_vat_number)]

# An ISO 4217 code such as SAR. Any code is accepted here; an unexpected currency is a finding, not a parse error.
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]

Text = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class _Contract(BaseModel):
    # forbid: an unknown field is an error, which catches typos and fields an LLM invents.
    # frozen: once validated, an invoice can't be changed by accident further down the pipeline.
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Party(_Contract):
    """The seller or the buyer. Names may be in Arabic, English or both."""

    name_en: Text | None = None
    name_ar: Text | None = None
    vat_number: VatNumber | None = None

    @model_validator(mode="after")
    def _has_a_name(self) -> "Party":
        if self.name_en is None and self.name_ar is None:
            raise ValueError("a party needs a name in English, Arabic or both")
        return self


class LineItem(_Contract):
    """One line of the invoice, with the amounts as printed."""

    description_en: Text | None = None
    description_ar: Text | None = None
    quantity: Quantity
    unit_price: Money
    vat_rate: VatRate
    line_total: Money  # excluding VAT, as stated on the invoice

    @model_validator(mode="after")
    def _has_a_description(self) -> "LineItem":
        if self.description_en is None and self.description_ar is None:
            raise ValueError("a line needs a description in English, Arabic or both")
        return self


class Invoice(_Contract):
    """A supplier invoice. Totals are the stated ones; `check_invoice` compares them with the lines."""

    invoice_number: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    invoice_type: Literal["standard", "simplified"]  # ZATCA: standard = B2B, simplified = B2C
    issue_date: date
    currency: Currency
    seller: Party
    buyer: Party | None = None
    lines: tuple[LineItem, ...] = Field(min_length=1)
    subtotal: Money  # total excluding VAT
    vat_total: Money
    total: Money  # total including VAT
