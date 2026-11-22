"""The buying side of the world: whom each company buys from, the prices it agreed, and what it ordered.

A buyer doesn't check a supplier's invoice against the invoice itself. It checks it against its own records:
is this a supplier we approved (the vendor master), is this the price we agreed (the price list), and did we
order this (the purchase order)? An invoice can only be wrong compared with something, and these records are
what the anomalies of lesson 1.7 are wrong against.

ZATCA leaves that matching to the buyer: its XML standard (version 1.2, section 6) lists "invoice
verification against a contract or purchase order" as out of its scope. An invoice may still carry the
order's number (cac:OrderReference), and the worked examples in ZATCA's invoicing guideline print it.
"""

import random
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from ledgerlens_datagen.world import CATALOGUE, Company, World

# How many suppliers each company has approved.
MIN_VENDORS = 4
MAX_VENDORS = 8


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Vendor(_Record):
    """A supplier on a buyer's vendor master, as the buyer recorded it when approving them."""

    vendor_number: str  # the buyer's own reference for this supplier
    vat_number: str
    name_en: str
    name_ar: str


class AgreedPrice(_Record):
    """The unit price, before VAT, that a buyer agreed with one of its vendors for one item."""

    vendor_vat_number: str
    description_en: str
    description_ar: str
    unit_price: Decimal


class BuyerRecords(_Record):
    """One company's purchasing records: the vendors it approved and the prices it agreed with each."""

    vat_number: str
    # Where this buyer's purchase-order numbers start. Each order adds its invoice's index, so the numbers
    # are unique for each buyer, and invoice n still depends only on the seed and n.
    first_order_number: int
    vendors: tuple[Vendor, ...]
    prices: tuple[AgreedPrice, ...]


class Purchasing(_Record):
    buyers: tuple[BuyerRecords, ...]  # one per company: every company buys as well as sells

    def records_of(self, vat_number: str) -> BuyerRecords:
        return {buyer.vat_number: buyer for buyer in self.buyers}[vat_number]


class OrderLine(_Record):
    description_en: str
    description_ar: str
    quantity: Decimal
    unit_price: Decimal  # the agreed price, before VAT


class PurchaseOrder(_Record):
    """What a buyer ordered from one of its vendors. The vendor's invoice bills it."""

    order_number: str
    buyer_vat_number: str
    vendor_vat_number: str
    order_date: date
    lines: tuple[OrderLine, ...]


def build_purchasing(seed: int, world: World) -> Purchasing:
    """The same seed always gives the same vendor masters and prices. They come from a random stream of
    their own, so the companies stay exactly those of build_world."""
    rng = random.Random(f"ledgerlens-datagen/{seed}/purchasing")
    return Purchasing(buyers=tuple(_records(rng, company, world.companies) for company in world.companies))


def _records(rng: random.Random, buyer: Company, companies: tuple[Company, ...]) -> BuyerRecords:
    others = [c for c in companies if c.vat_number != buyer.vat_number]
    suppliers = rng.sample(others, rng.randint(MIN_VENDORS, MAX_VENDORS))
    numbers = sorted(rng.sample(range(10_000, 100_000), len(suppliers)))
    return BuyerRecords(
        vat_number=buyer.vat_number,
        first_order_number=rng.randint(100_000, 899_999),
        vendors=tuple(
            Vendor(vendor_number=f"V-{number}", vat_number=s.vat_number, name_en=s.name_en, name_ar=s.name_ar)
            for number, s in zip(numbers, suppliers, strict=True)
        ),
        # A price for everything each vendor sells. Two vendors in the same trade agree different prices.
        prices=tuple(
            AgreedPrice(
                vendor_vat_number=s.vat_number,
                description_en=item.en,
                description_ar=item.ar,
                unit_price=item.price(rng),
            )
            for s in suppliers
            for item in CATALOGUE[s.trade]
        ),
    )
