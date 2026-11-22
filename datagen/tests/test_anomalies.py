"""Labelled anomalies and drift.

broken_rules() checks an invoice the way a reviewer with the buyer's records would. Every anomaly must break
exactly the rule its label names and no other, and a clean invoice must break none, or the labels would
teach a model the wrong thing. These rules are also the baseline Module 5's review agents must beat.
"""

import json
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ledgerlens.contracts.checks import check_invoice
from ledgerlens_datagen import qr
from ledgerlens_datagen.anomalies import (
    DUPLICATE_WINDOW,
    Settings,
    drifted_vendors,
    generate_labelled,
    labelled_invoice,
)
from ledgerlens_datagen.generate import SyntheticInvoice, generate, generate_invoice
from ledgerlens_datagen.labels import ANOMALY_TYPES, AnomalyType
from ledgerlens_datagen.purchasing import build_purchasing
from ledgerlens_datagen.world import build_world

SEED = 20261109
MIXED = list(generate_labelled(SEED, 1000, Settings(anomaly_rate=0.3)))
DRIFT_FROM = date(2026, 6, 1)
DRIFTED = list(generate_labelled(SEED, 3000, Settings(drift_from=DRIFT_FROM)))

# The one rule each anomaly breaks. vat_total_mismatch and total_mismatch are check_invoice's own codes.
BREAKS: dict[AnomalyType | None, set[str]] = {
    None: set(),
    "duplicate_exact": {"repeated_number"},
    "duplicate_near": {"repeated_bill"},
    "price_above_agreed": {"price_not_agreed"},
    "quantity_above_ordered": {"quantity_not_ordered"},
    "vat_wrong": {"vat_total_mismatch"},
    "total_inflated": {"total_mismatch"},
    "qr_mismatch": {"qr_disagrees"},
}


def broken_rules(s: SyntheticInvoice, earlier: Sequence[SyntheticInvoice]) -> set[str]:
    broken = {finding.code for finding in check_invoice(s.invoice)}
    if s.purchase_order is not None:
        for line, ordered in zip(s.invoice.lines, s.purchase_order.lines, strict=True):
            if line.unit_price != ordered.unit_price:
                broken.add("price_not_agreed")
            if line.quantity > ordered.quantity:
                broken.add("quantity_not_ordered")
    tags = qr.decode(s.qr_code)
    if (tags[4], tags[5]) != (f"{s.invoice.total:.2f}".encode(), f"{s.invoice.vat_total:.2f}".encode()):
        broken.add("qr_disagrees")
    same_seller = [e for e in earlier if e.invoice.seller.vat_number == s.invoice.seller.vat_number]
    # The number first: an invoice that repeats a number is reported for that alone.
    if any(e.invoice.invoice_number == s.invoice.invoice_number for e in same_seller):
        broken.add("repeated_number")
    # Then the bill itself. The same lines and total aren't enough: a monthly contract bills the same amount
    # every month, under a new order each time. A bill sent twice repeats the order too.
    elif any(_bill(e) == _bill(s) for e in same_seller):
        broken.add("repeated_bill")
    return broken


def _bill(s: SyntheticInvoice) -> tuple[object, ...]:
    return s.invoice.purchase_order_number, s.invoice.lines, s.invoice.total


def _kind(s: SyntheticInvoice) -> AnomalyType | None:
    return None if s.anomaly is None else s.anomaly.type


def test_every_invoice_breaks_exactly_the_rule_its_label_names() -> None:
    for n, s in enumerate(MIXED):
        assert broken_rules(s, MIXED[:n]) == BREAKS[_kind(s)], (n, _kind(s))


def test_every_kind_appears_at_about_the_asked_rate() -> None:
    counts = Counter(_kind(s) for s in MIXED)
    assert set(counts) == {None, *ANOMALY_TYPES}
    assert 0.25 < 1 - counts[None] / len(MIXED) < 0.35


def test_anomalies_leave_the_clean_invoices_as_they_were() -> None:
    clean = list(generate(SEED, len(MIXED)))
    assert [s for s in MIXED if s.anomaly is None] == [
        c for c, s in zip(clean, MIXED, strict=True) if s.anomaly is None
    ]


def test_a_duplicate_repeats_a_clean_invoice_shortly_before_it() -> None:
    for s in MIXED:
        if s.anomaly is None or s.anomaly.duplicate_of is None:
            assert _kind(s) not in ("duplicate_exact", "duplicate_near")
            continue
        original = MIXED[s.anomaly.duplicate_of]
        assert original.anomaly is None
        assert 0 < s.index - original.index <= DUPLICATE_WINDOW
        if s.anomaly.type == "duplicate_exact":
            assert s.model_copy(update={"index": original.index, "anomaly": None}) == original
        else:
            # The same order billed again, a few days later, under a new number.
            assert s.purchase_order == original.purchase_order
            assert s.invoice.invoice_number != original.invoice.invoice_number
            assert 1 <= (s.invoice.issue_date - original.invoice.issue_date).days <= 14


def _value_at(data: Any, path: str) -> Any:
    for key in path.split("."):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def test_each_label_points_at_values_the_page_prints() -> None:
    # The same paths as the page's boxes, so a reviewer's screen can highlight them.
    printed = {"invoice.invoice_number", "invoice.total", "invoice.vat_total", "qr_code"}
    for s in MIXED:
        if s.anomaly is not None:
            data = json.loads(s.model_dump_json())
            for field in s.anomaly.fields:
                assert field in printed or field.rsplit(".", 1)[-1] in ("unit_price", "quantity"), field
                assert _value_at(data, field) is not None


@settings(max_examples=100, deadline=None)
@given(seed=st.integers(0, 2**32 - 1), index=st.integers(0, 100_000))
def test_any_clean_invoice_breaks_no_rule(seed: int, index: int) -> None:
    world = build_world(seed)
    assert broken_rules(generate_invoice(world, build_purchasing(seed, world), seed, index), []) == set()


@settings(max_examples=150, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    index=st.integers(1, DUPLICATE_WINDOW),
    kind=st.sampled_from(ANOMALY_TYPES),
)
def test_any_anomaly_on_any_invoice_breaks_exactly_its_own_rule(seed: int, index: int, kind: AnomalyType) -> None:
    world = build_world(seed)
    purchasing = build_purchasing(seed, world)
    s = labelled_invoice(world, purchasing, seed, index, Settings(anomaly_rate=1, types=(kind,)))
    # Not every invoice can have every anomaly: a simplified invoice has no order to bill above.
    assume(s.anomaly is not None)
    assert _kind(s) == kind
    original = s.anomaly.duplicate_of if s.anomaly else None
    earlier = [] if original is None else [generate_invoice(world, purchasing, seed, original)]
    assert broken_rules(s, earlier) == BREAKS[kind]


def test_with_every_invoice_anomalous_a_duplicate_has_nothing_to_repeat_and_stays_clean() -> None:
    every = list(generate_labelled(SEED, 40, Settings(anomaly_rate=1)))
    assert all(_kind(s) not in ("duplicate_exact", "duplicate_near") for s in every)
    assert sum(s.anomaly is None for s in every) > 0


def test_drift_moves_some_vendors_to_design_b_from_the_chosen_date() -> None:
    vendors = drifted_vendors(SEED, build_world(SEED))
    assert len(vendors) == 12
    for s in DRIFTED:
        drifted = s.invoice.issue_date >= DRIFT_FROM and s.invoice.seller.vat_number in vendors
        assert s.design == ("b" if drifted else "a")
    assert Counter(s.design for s in DRIFTED)["b"] > 300


def test_drift_makes_anomalies_about_twice_as_common() -> None:
    def share(group: list[SyntheticInvoice]) -> float:
        return sum(s.anomaly is not None for s in group) / len(group)

    before = [s for s in DRIFTED if s.invoice.issue_date < DRIFT_FROM]
    after = [s for s in DRIFTED if s.invoice.issue_date >= DRIFT_FROM]
    assert 1.5 < share(after) / share(before) < 2.5
