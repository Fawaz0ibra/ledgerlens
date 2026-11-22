"""Turn a seed into invoices. The same seed and index always give the same invoice.

Each invoice gets its own random generator, seeded from (seed, index). So invoice 41 is the same whether
we make 50 invoices or 5,000, and invoices can later be made in parallel. A str seed is turned into a
number with SHA-512, so Python's per-process hash randomisation doesn't change it.

A standard invoice starts on the buying side (purchasing.py): a company orders from a supplier it approved, at
the prices they agreed, and the supplier's invoice bills that order. A simplified invoice is a sale to a
consumer, at the shelf price, with no order behind it.

The amounts are built the way check_invoice reads them, so a clean invoice has no findings. anomalies.py
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
from ledgerlens_datagen.labels import Anomaly, Design
from ledgerlens_datagen.purchasing import BuyerRecords, OrderLine, PurchaseOrder, Purchasing, build_purchasing
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
# A supplier invoices an order on the day it was placed or up to this many days later.
MAX_DAYS_TO_INVOICE = 30


class LineVat(BaseModel):
    """What the page prints for a line beyond the contract's line item: its VAT, and its amount with VAT."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    vat_amount: Decimal  # rounded per line
    amount_with_vat: Decimal


class SyntheticInvoice(BaseModel):
    """One synthetic invoice: the contract invoice, plus what the page shows that the contract doesn't hold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int
    index: int
    invoice: Invoice
    issued_at: datetime  # Riyadh time; the date is invoice.issue_date
    seller_address: Address
    buyer_address: Address | None
    # The order a standard invoice bills, as the buyer's records hold it. None on a simplified invoice.
    purchase_order: PurchaseOrder | None
    qr_code: str  # the Base64 text the QR code holds
    # One per invoice line. ZATCA asks for VAT per line on a tax invoice; the contract holds VAT only as a
    # total, rounded once over the subtotal, so the lines' VAT can differ from it by a halala or two.
    line_vat: tuple[LineVat, ...]
    anomaly: Anomaly | None = None  # None: a clean invoice
    design: Design = "a"


def generate(seed: int, count: int) -> Iterator[SyntheticInvoice]:
    """Clean invoices only. anomalies.generate_labelled adds labelled anomalies and drift on top of these."""
    world = build_world(seed)
    purchasing = build_purchasing(seed, world)
    for index in range(count):
        yield generate_invoice(world, purchasing, seed, index)


def generate_invoice(world: World, purchasing: Purchasing, seed: int, index: int) -> SyntheticInvoice:
    rng = random.Random(f"ledgerlens-datagen/{seed}/{index}")
    kind: Literal["standard", "simplified"] = "standard" if rng.random() < STANDARD_SHARE else "simplified"
    day = FIRST_DAY + timedelta(days=rng.randint(0, (LAST_DAY - FIRST_DAY).days))
    issued_at = datetime.combine(day, time(rng.randint(8, 21), rng.randint(0, 59), rng.randint(0, 59)), RIYADH)

    buyer: Company | None
    order: PurchaseOrder | None
    if kind == "standard":
        # A standard invoice names a VAT-registered buyer: a company, which ordered from a supplier it approved.
        buyer = rng.choice(world.companies)
        records = purchasing.records_of(buyer.vat_number)
        seller = world.company(rng.choice(records.vendors).vat_number)
        order = _purchase_order(rng, records, seller, day, index)
        lines = tuple(_billed(line) for line in order.lines)
    else:
        # A simplified one goes to a consumer, at the shelf price, with no order.
        buyer = None
        order = None
        seller = rng.choice(world.companies)
        catalogue = CATALOGUE[seller.trade]
        lines = tuple(
            _line(item.en, item.ar, _quantity(rng, item), item.price(rng))
            for item in rng.sample(catalogue, rng.randint(1, MAX_SIMPLIFIED_LINES))
        )
    subtotal = sum((line.line_total for line in lines), Decimal(0))
    vat_total = round_to_halala(subtotal * VAT_RATE)

    invoice = Invoice(
        invoice_number=seller.invoice_number(day.year, index + 1),
        invoice_type=kind,
        issue_date=day,
        currency="SAR",
        purchase_order_number=None if order is None else order.order_number,
        seller=_party(seller),
        buyer=None if buyer is None else _party(buyer),
        lines=lines,
        subtotal=subtotal,
        vat_total=vat_total,
        total=subtotal + vat_total,
    )
    return SyntheticInvoice(
        seed=seed,
        index=index,
        invoice=invoice,
        issued_at=issued_at,
        seller_address=seller.address,
        buyer_address=None if buyer is None else buyer.address,
        purchase_order=order,
        qr_code=_qr_code(seller, issued_at, invoice.total, invoice.vat_total),
        line_vat=tuple(_line_vat(line) for line in lines),
    )


def restate(
    s: SyntheticInvoice,
    seller: Company,
    *,
    lines: tuple[LineItem, ...] | None = None,
    invoice_number: str | None = None,
    issued_at: datetime | None = None,
    vat_total: Decimal | None = None,
    added_to_total: Decimal = Decimal(0),
    qr_total: Decimal | None = None,
) -> SyntheticInvoice:
    """The invoice with some printed values changed, and every amount that follows from them worked out
    again. An anomaly changes one thing, and the rest of the page stays consistent with it.

    vat_total, added_to_total and qr_total break that consistency on purpose: a VAT total that doesn't
    follow from the lines, a total more than the subtotal plus the VAT, a QR code that holds another total.
    """
    lines = s.invoice.lines if lines is None else lines
    issued_at = s.issued_at if issued_at is None else issued_at
    subtotal = sum((line.line_total for line in lines), Decimal(0))
    vat = round_to_halala(subtotal * VAT_RATE) if vat_total is None else vat_total
    invoice = Invoice.model_validate(
        {
            **s.invoice.model_dump(),
            "invoice_number": s.invoice.invoice_number if invoice_number is None else invoice_number,
            "issue_date": issued_at.date(),
            "lines": lines,
            "subtotal": subtotal,
            "vat_total": vat,
            "total": subtotal + vat + added_to_total,
        }
    )
    qr_code = _qr_code(seller, issued_at, invoice.total if qr_total is None else qr_total, invoice.vat_total)
    return s.model_copy(
        update={
            "invoice": invoice,
            "issued_at": issued_at,
            "qr_code": qr_code,
            "line_vat": tuple(_line_vat(line) for line in lines),
        }
    )


def _qr_code(seller: Company, issued_at: datetime, total: Decimal, vat_total: Decimal) -> str:
    return qr.encode(
        qr.QrFields(
            # The Arabic name: ZATCA treats the Arabic text as the legally binding one.
            seller_name=seller.name_ar,
            vat_number=seller.vat_number,
            issued_at=issued_at,
            total=total,
            vat_total=vat_total,
        )
    )


def _purchase_order(rng: random.Random, buyer: BuyerRecords, vendor: Company, day: date, index: int) -> PurchaseOrder:
    """What the buyer ordered: some of what the vendor sells, at the prices they agreed."""
    agreed = {p.description_en: p.unit_price for p in buyer.prices if p.vendor_vat_number == vendor.vat_number}
    catalogue = CATALOGUE[vendor.trade]
    return PurchaseOrder(
        order_number=f"PO-{buyer.first_order_number + index}",
        buyer_vat_number=buyer.vat_number,
        vendor_vat_number=vendor.vat_number,
        order_date=day - timedelta(days=rng.randint(0, MAX_DAYS_TO_INVOICE)),
        lines=tuple(
            OrderLine(
                description_en=item.en,
                description_ar=item.ar,
                quantity=_quantity(rng, item),
                unit_price=agreed[item.en],
            )
            for item in rng.sample(catalogue, rng.randint(1, len(catalogue)))
        ),
    )


def _billed(line: OrderLine) -> LineItem:
    """An invoice line for an order line: what was ordered, at the agreed price."""
    return _line(line.description_en, line.description_ar, line.quantity, line.unit_price)


def _line_vat(line: LineItem) -> LineVat:
    vat_amount = round_to_halala(line.line_total * line.vat_rate)
    return LineVat(vat_amount=vat_amount, amount_with_vat=line.line_total + vat_amount)


def _party(company: Company) -> Party:
    return Party(name_en=company.name_en, name_ar=company.name_ar, vat_number=company.vat_number)


def _line(description_en: str, description_ar: str, quantity: Decimal, unit_price: Decimal) -> LineItem:
    return LineItem(
        description_en=description_en,
        description_ar=description_ar,
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


def round_to_halala(amount: Decimal) -> Decimal:
    """The same rounding check_invoice uses: to the halala, halves up."""
    return amount.quantize(HALALA, rounding=ROUND_HALF_UP)
