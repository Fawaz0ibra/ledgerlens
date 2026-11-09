"""Turn a seed into invoices. The same seed and index always give the same invoice.

Each invoice gets its own random generator, seeded from (seed, index). So invoice 41 is the same whether
we make 50 invoices or 5,000, and invoices can later be made in parallel. A str seed is turned into a
number with SHA-512, so Python's per-process hash randomisation doesn't change it.

The amounts are built the way check_invoice reads them, so a clean invoice has no findings. Lesson 1.7
breaks them on purpose, one labelled anomaly at a time.
"""

import random
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, assert_never

from pydantic import BaseModel, ConfigDict

from ledgerlens.contracts.checks import HALALA
from ledgerlens.contracts.invoice import Invoice, LineItem, Party
from ledgerlens_datagen import qr
from ledgerlens_datagen.world import CATALOGUE, Address, Company, Item, World, build_world

# Saudi Arabia is UTC+3 all year (no daylight saving), so a fixed offset is exact and needs no time zone data.
RIYADH = timezone(timedelta(hours=3))
VAT_RATE = Decimal("0.15")
# The share of standard (business-to-business) invoices; the rest are simplified (to consumers).
STANDARD_SHARE = 0.7
# Simplified invoices are usually small: a few lines.
MAX_SIMPLIFIED_LINES = 3
FIRST_DAY = date(2026, 1, 1)
LAST_DAY = date(2026, 10, 31)


class SyntheticInvoice(BaseModel):
    """One synthetic invoice: the contract invoice, plus what the page shows that the contract doesn't hold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int
    index: int
    invoice: Invoice
    issued_at: datetime  # Riyadh time; the date is invoice.issue_date
    seller_address: Address
    buyer_address: Address | None
    qr_code: str  # the Base64 text the QR code holds


def generate(seed: int, count: int) -> Iterator[SyntheticInvoice]:
    world = build_world(seed)
    for index in range(count):
        yield generate_invoice(world, seed, index)


def generate_invoice(world: World, seed: int, index: int) -> SyntheticInvoice:
    rng = random.Random(f"ledgerlens-datagen/{seed}/{index}")
    seller = rng.choice(world.companies)
    kind: Literal["standard", "simplified"] = "standard" if rng.random() < STANDARD_SHARE else "simplified"
    # A standard invoice names a VAT-registered buyer: another company. A simplified one goes to a consumer.
    catalogue = CATALOGUE[seller.trade]
    if kind == "standard":
        buyer: Company | None = rng.choice([c for c in world.companies if c.vat_number != seller.vat_number])
        most_lines = len(catalogue)
    else:
        buyer = None
        most_lines = MAX_SIMPLIFIED_LINES
    lines = tuple(_line(rng, item) for item in rng.sample(catalogue, rng.randint(1, most_lines)))
    subtotal = sum((line.line_total for line in lines), Decimal(0))
    vat_total = round_to_halala(subtotal * VAT_RATE)

    day = FIRST_DAY + timedelta(days=rng.randint(0, (LAST_DAY - FIRST_DAY).days))
    issued_at = datetime.combine(day, time(rng.randint(8, 21), rng.randint(0, 59), rng.randint(0, 59)), RIYADH)

    invoice = Invoice(
        invoice_number=seller.invoice_number(day.year, index + 1),
        invoice_type=kind,
        issue_date=day,
        currency="SAR",
        seller=_party(seller),
        buyer=None if buyer is None else _party(buyer),
        lines=lines,
        subtotal=subtotal,
        vat_total=vat_total,
        total=subtotal + vat_total,
    )
    qr_code = qr.encode(
        qr.QrFields(
            # The Arabic name: ZATCA treats the Arabic text as the legally binding one.
            seller_name=seller.name_ar,
            vat_number=seller.vat_number,
            issued_at=issued_at,
            total=invoice.total,
            vat_total=invoice.vat_total,
        )
    )
    return SyntheticInvoice(
        seed=seed,
        index=index,
        invoice=invoice,
        issued_at=issued_at,
        seller_address=seller.address,
        buyer_address=None if buyer is None else buyer.address,
        qr_code=qr_code,
    )


def _party(company: Company) -> Party:
    return Party(name_en=company.name_en, name_ar=company.name_ar, vat_number=company.vat_number)


def _line(rng: random.Random, item: Item) -> LineItem:
    quantity = _quantity(rng, item)
    unit_price = _price(rng, item)
    return LineItem(
        description_en=item.en,
        description_ar=item.ar,
        quantity=quantity,
        unit_price=unit_price,
        vat_rate=VAT_RATE,
        line_total=round_to_halala(quantity * unit_price),
    )


def _quantity(rng: random.Random, item: Item) -> Decimal:
    # Built from whole numbers, so every quantity is an exact Decimal: no float ever touches the money.
    match item.unit:
        case "each":
            return Decimal(rng.randint(1, item.max_quantity))
        case "hour":
            return Decimal(rng.randint(1, 2 * item.max_quantity)) / 2  # to the half hour
        case "kg":
            return Decimal(rng.randint(500, 1000 * item.max_quantity)) / 1000  # to the gram
        case _:  # pragma: no cover (unreachable: mypy fails here if a new unit isn't handled above)
            assert_never(item.unit)


def _price(rng: random.Random, item: Item) -> Decimal:
    riyals = rng.randint(item.min_price, item.max_price)
    # Most prices are whole riyals, some end in .50, and some have any halalas.
    style = rng.random()
    if style < 0.6:
        halalas = 0
    elif style < 0.8:
        halalas = 50
    else:
        halalas = rng.randint(1, 99)
    # Built as text: Decimal("122.00") keeps both decimal places, where Decimal(12200) / 100 gives Decimal("122").
    return Decimal(f"{riyals}.{halalas:02d}")


def round_to_halala(amount: Decimal) -> Decimal:
    """The same rounding check_invoice uses: to the halala, halves up."""
    return amount.quantize(HALALA, rounding=ROUND_HALF_UP)
