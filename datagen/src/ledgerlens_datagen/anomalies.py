"""Labelled anomalies and controlled drift, on top of the clean invoices of generate.py.

Whether invoice n gets an anomaly is drawn from a random stream of its own, so turning anomalies on or off
never changes the clean invoices: invoice n without an anomaly is exactly the invoice generate() makes. An
invoice carries at most one anomaly. With two, an evaluation couldn't tell which mistake a model caught.

Drift starts on a chosen issue date. From then on, some vendors draw their invoices with a new design (a
change in what a model sees) and anomalies come twice as often (a change in what it should find).
"""

import random
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field

from ledgerlens.contracts.invoice import LineItem
from ledgerlens_datagen.generate import VAT_RATE, SyntheticInvoice, generate_invoice, restate, round_to_halala
from ledgerlens_datagen.labels import ANOMALY_TYPES, Anomaly, AnomalyType, Design
from ledgerlens_datagen.purchasing import Purchasing, build_purchasing
from ledgerlens_datagen.world import Company, World, build_world

# About one invoice in twenty. Real rates vary by company; a test set for one anomaly can ask for more.
DEFAULT_RATE = 0.05
# A duplicate repeats one of the clean invoices shortly before it.
DUPLICATE_WINDOW = 30
# Once drift starts: the share of vendors that switch to design b, and how much more often anomalies come.
DRIFTED_VENDOR_SHARE = 0.3
DRIFT_RATE_FACTOR = 2


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    anomaly_rate: float = Field(default=DEFAULT_RATE, ge=0, le=1)
    # Which anomalies to draw from, evenly among those an invoice can have.
    types: tuple[AnomalyType, ...] = ANOMALY_TYPES
    drift_from: date | None = None  # no drift when None


def generate_labelled(seed: int, count: int, settings: Settings | None = None) -> Iterator[SyntheticInvoice]:
    world = build_world(seed)
    purchasing = build_purchasing(seed, world)
    for index in range(count):
        yield labelled_invoice(world, purchasing, seed, index, settings or Settings())


def labelled_invoice(
    world: World, purchasing: Purchasing, seed: int, index: int, settings: Settings
) -> SyntheticInvoice:
    clean = generate_invoice(world, purchasing, seed, index)
    rng = _anomaly_rng(seed, index)
    seller = _seller(world, clean)
    labelled = clean
    drawn = _draw(rng, clean, settings)
    match drawn:
        case None:
            pass
        case "duplicate_exact" | "duplicate_near":
            original = _clean_original(world, purchasing, seed, index, settings, rng)
            # Without a clean invoice shortly before it there is nothing to repeat, so it stays clean.
            if original is not None:
                labelled = _duplicate(drawn, original, index, _seller(world, original), rng)
        case "price_above_agreed":
            n, line = _some_line(clean, rng)
            raised = round_to_halala(line.unit_price * (100 + rng.choice((3, 5, 8, 10, 15))) / 100)
            lines = _with_line(clean, n, line.quantity, raised)
            labelled = _label(restate(clean, seller, lines=lines), drawn, f"invoice.lines.{n}.unit_price")
        case "quantity_above_ordered":
            n, line = _some_line(clean, rng)
            lines = _with_line(clean, n, line.quantity + rng.randint(1, 5), line.unit_price)
            labelled = _label(restate(clean, seller, lines=lines), drawn, f"invoice.lines.{n}.quantity")
        case "vat_wrong":
            left_out = rng.choice(clean.invoice.lines)
            vat_total = round_to_halala((clean.invoice.subtotal - left_out.line_total) * VAT_RATE)
            labelled = _label(restate(clean, seller, vat_total=vat_total), drawn, "invoice.vat_total")
        case "total_inflated":
            extra = rng.choice((Decimal("10.00"), Decimal("90.00"), Decimal("100.00"), Decimal("900.00")))
            labelled = _label(restate(clean, seller, added_to_total=extra), drawn, "invoice.total")
        case "qr_mismatch":
            # A common slip: the QR code gets the amount before VAT.
            restated = restate(clean, seller, qr_total=clean.invoice.subtotal)
            labelled = _label(restated, drawn, "qr_code")
        case _:  # pragma: no cover (unreachable: mypy fails here if a new type isn't handled above)
            assert_never(drawn)
    return labelled.model_copy(update={"design": design_of(seed, world, labelled, settings)})


def drifted_vendors(seed: int, world: World) -> frozenset[str]:
    """The VAT numbers of the vendors that switch to design b once drift starts."""
    rng = random.Random(f"ledgerlens-datagen/{seed}/drift")
    chosen = rng.sample(world.companies, round(DRIFTED_VENDOR_SHARE * len(world.companies)))
    return frozenset(company.vat_number for company in chosen)


def design_of(seed: int, world: World, s: SyntheticInvoice, settings: Settings) -> Design:
    if _drifted(s, settings) and s.invoice.seller.vat_number in drifted_vendors(seed, world):
        return "b"
    return "a"


def _drifted(s: SyntheticInvoice, settings: Settings) -> bool:
    return settings.drift_from is not None and s.invoice.issue_date >= settings.drift_from


def _anomaly_rng(seed: int, index: int) -> random.Random:
    return random.Random(f"ledgerlens-datagen/{seed}/{index}/anomaly")


def _draw(rng: random.Random, clean: SyntheticInvoice, settings: Settings) -> AnomalyType | None:
    """Whether this invoice gets an anomaly, and which. It depends only on the invoice itself, never on the
    invoices around it, so finding a clean invoice for a duplicate to repeat can't go round in circles."""
    rate = settings.anomaly_rate * (DRIFT_RATE_FACTOR if _drifted(clean, settings) else 1)
    if rng.random() >= rate:
        return None
    possible = [kind for kind in settings.types if _possible(kind, clean)]
    return rng.choice(possible) if possible else None


def _possible(kind: AnomalyType, clean: SyntheticInvoice) -> bool:
    match kind:
        case "duplicate_exact" | "duplicate_near":
            return clean.index > 0
        case "price_above_agreed" | "quantity_above_ordered":
            return clean.purchase_order is not None  # checked against the order
        case "vat_wrong":
            return len(clean.invoice.lines) > 1  # it leaves one line out
        case "total_inflated" | "qr_mismatch":
            return True
        case _:  # pragma: no cover (unreachable: mypy fails here if a new type isn't handled above)
            assert_never(kind)


def _clean_original(
    world: World, purchasing: Purchasing, seed: int, index: int, settings: Settings, rng: random.Random
) -> SyntheticInvoice | None:
    candidates = []
    for earlier in range(max(0, index - DUPLICATE_WINDOW), index):
        invoice = generate_invoice(world, purchasing, seed, earlier)
        if _draw(_anomaly_rng(seed, earlier), invoice, settings) is None:
            candidates.append(invoice)
    return rng.choice(candidates) if candidates else None


def _duplicate(
    kind: AnomalyType, original: SyntheticInvoice, index: int, seller: Company, rng: random.Random
) -> SyntheticInvoice:
    anomaly = Anomaly(type=kind, fields=("invoice.invoice_number",), duplicate_of=original.index)
    if kind == "duplicate_near":
        # Sent again a few days later, under the seller's next number: only the bill itself gives it away.
        issued_at = original.issued_at + timedelta(days=rng.randint(1, 14))
        number = seller.invoice_number(issued_at.year, index + 1)
        original = restate(original, seller, invoice_number=number, issued_at=issued_at)
        anomaly = anomaly.model_copy(update={"fields": ("invoice.invoice_number", "invoice.total")})
    return original.model_copy(update={"index": index, "anomaly": anomaly})


def _some_line(clean: SyntheticInvoice, rng: random.Random) -> tuple[int, LineItem]:
    n = rng.randrange(len(clean.invoice.lines))
    return n, clean.invoice.lines[n]


def _with_line(clean: SyntheticInvoice, n: int, quantity: Decimal, unit_price: Decimal) -> tuple[LineItem, ...]:
    """The invoice's lines, with line n billing this quantity at this price."""
    lines = clean.invoice.lines
    line = lines[n].model_copy(
        update={"quantity": quantity, "unit_price": unit_price, "line_total": round_to_halala(quantity * unit_price)}
    )
    return (*lines[:n], line, *lines[n + 1 :])


def _label(s: SyntheticInvoice, kind: AnomalyType, field: str) -> SyntheticInvoice:
    return s.model_copy(update={"anomaly": Anomaly(type=kind, fields=(field,))})


def _seller(world: World, s: SyntheticInvoice) -> Company:
    vat_number = s.invoice.seller.vat_number
    assert vat_number is not None  # every synthetic seller has one
    return world.company(vat_number)
