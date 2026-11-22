"""The buying side: every company's approved vendors and agreed prices, and the order behind every standard
invoice, which a clean invoice bills exactly."""

from datetime import timedelta

from ledgerlens_datagen.generate import generate
from ledgerlens_datagen.purchasing import MAX_VENDORS, MIN_VENDORS, build_purchasing
from ledgerlens_datagen.world import CATALOGUE, build_world

SEED = 20261109
WORLD = build_world(SEED)
PURCHASING = build_purchasing(SEED, WORLD)
INVOICES = list(generate(SEED, 500))
STANDARD = [s for s in INVOICES if s.invoice.invoice_type == "standard"]


def test_every_company_buys_from_its_own_list_of_other_companies() -> None:
    assert [b.vat_number for b in PURCHASING.buyers] == [c.vat_number for c in WORLD.companies]
    for buyer in PURCHASING.buyers:
        vendors = [v.vat_number for v in buyer.vendors]
        assert MIN_VENDORS <= len(vendors) <= MAX_VENDORS
        assert len(set(vendors)) == len(vendors)
        assert buyer.vat_number not in vendors
        assert len({v.vendor_number for v in buyer.vendors}) == len(vendors)


def test_the_vendor_master_holds_each_supplier_as_it_really_is() -> None:
    for buyer in PURCHASING.buyers:
        for vendor in buyer.vendors:
            company = WORLD.company(vendor.vat_number)
            assert (vendor.name_en, vendor.name_ar) == (company.name_en, company.name_ar)


def test_each_buyer_agreed_a_price_for_everything_its_vendors_sell() -> None:
    for buyer in PURCHASING.buyers:
        assert len(buyer.prices) == sum(len(CATALOGUE[WORLD.company(v.vat_number).trade]) for v in buyer.vendors)
        for vendor in buyer.vendors:
            catalogue = CATALOGUE[WORLD.company(vendor.vat_number).trade]
            agreed = {p.description_en: p.unit_price for p in buyer.prices if p.vendor_vat_number == vendor.vat_number}
            assert sorted(agreed) == sorted(item.en for item in catalogue)
            for item in catalogue:
                assert item.min_price <= agreed[item.en] < item.max_price + 1
                assert agreed[item.en].as_tuple().exponent == -2


def test_vendors_in_the_same_trade_agree_different_prices() -> None:
    # Otherwise "the agreed price" would just be the catalogue's, and checking against the buyer's own
    # records would teach nothing a price list for the whole world couldn't.
    prices: dict[str, set[object]] = {}
    for buyer in PURCHASING.buyers:
        for price in buyer.prices:
            prices.setdefault(price.description_en, set()).add(price.unit_price)
    assert all(len(seen) > 1 for seen in prices.values())


def test_a_simplified_invoice_bills_no_order() -> None:
    for s in INVOICES:
        if s.invoice.invoice_type == "simplified":
            assert s.purchase_order is None
            assert s.invoice.purchase_order_number is None


def test_every_standard_invoice_bills_an_order_its_buyer_placed_with_an_approved_vendor() -> None:
    assert len(STANDARD) > 300
    for s in STANDARD:
        order, invoice = s.purchase_order, s.invoice
        assert order is not None
        assert invoice.buyer is not None
        assert invoice.purchase_order_number == order.order_number
        assert order.buyer_vat_number == invoice.buyer.vat_number
        assert order.vendor_vat_number == invoice.seller.vat_number
        approved = {v.vat_number for v in PURCHASING.records_of(order.buyer_vat_number).vendors}
        assert order.vendor_vat_number in approved
        assert timedelta(0) <= invoice.issue_date - order.order_date <= timedelta(days=30)


def test_a_clean_invoice_bills_exactly_what_was_ordered_at_the_agreed_prices() -> None:
    for s in STANDARD:
        order = s.purchase_order
        assert order is not None
        billed = [
            (line.description_en, line.description_ar, line.quantity, line.unit_price) for line in s.invoice.lines
        ]
        ordered = [(line.description_en, line.description_ar, line.quantity, line.unit_price) for line in order.lines]
        assert billed == ordered
        buyer = PURCHASING.records_of(order.buyer_vat_number)
        agreed = {
            p.description_en: p.unit_price for p in buyer.prices if p.vendor_vat_number == order.vendor_vat_number
        }
        assert all(line.unit_price == agreed[line.description_en] for line in order.lines)


def test_order_numbers_are_unique_for_each_buyer() -> None:
    orders = [(s.purchase_order.buyer_vat_number, s.purchase_order.order_number) for s in STANDARD if s.purchase_order]
    assert len(set(orders)) == len(orders)


def test_the_same_seed_gives_the_same_records() -> None:
    assert build_purchasing(SEED, build_world(SEED)) == PURCHASING
    assert build_purchasing(SEED + 1, build_world(SEED + 1)) != PURCHASING
