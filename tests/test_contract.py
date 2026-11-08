"""The contract checks shape. A malformed invoice is rejected, with every problem named by its field."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from ledgerlens.contracts import Invoice


def problems(error: ValidationError) -> set[tuple[str, str]]:
    """Each problem as (field, error type), for example ("lines.0.unit_price", "decimal_max_places")."""
    return {(".".join(str(part) for part in e["loc"]), e["type"]) for e in error.errors()}


def test_the_sample_invoice_parses(invoice_data: dict[str, Any]) -> None:
    invoice = Invoice.model_validate(invoice_data)
    assert invoice.total == Decimal("493.35")
    assert [line.line_total for line in invoice.lines] == [Decimal("250.00"), Decimal("179.00")]


@pytest.mark.parametrize(
    ("changes", "field", "error_type"),
    [
        pytest.param(
            {"seller.vat_number": "39999999990001"},
            "seller.vat_number",
            "string_pattern_mismatch",
            id="vat-number-14-digits",
        ),
        pytest.param({"currency": "sar"}, "currency", "string_pattern_mismatch", id="currency-lowercase"),
        pytest.param({"invoice_type": "proforma"}, "invoice_type", "literal_error", id="unknown-invoice-type"),
        pytest.param(
            {"lines.0.unit_price": "25.001"}, "lines.0.unit_price", "decimal_max_places", id="price-3-decimals"
        ),
        pytest.param({"lines.0.quantity": "0"}, "lines.0.quantity", "greater_than", id="zero-quantity"),
        pytest.param({"total": "-1.00"}, "total", "greater_than_equal", id="negative-total"),
        pytest.param({"lines": []}, "lines", "too_short", id="no-lines"),
        pytest.param(
            {"seller.name_en": None, "seller.name_ar": None}, "seller", "value_error", id="seller-without-name"
        ),
        pytest.param(
            {"lines.0.description_en": None, "lines.0.description_ar": None},
            "lines.0",
            "value_error",
            id="line-without-description",
        ),
        pytest.param({"discount": "5.00"}, "discount", "extra_forbidden", id="unknown-field"),
        # A VAT number is an identifier, not an amount: sent as a number, it is refused.
        pytest.param(
            {"seller.vat_number": 399999999900013}, "seller.vat_number", "string_type", id="vat-number-as-number"
        ),
        # Lesson 1.1: 0.1 + 0.2 is the float 0.30000000000000004, and its 17 digits break the 15-digit limit.
        pytest.param(
            {"lines.0.unit_price": 0.1 + 0.2}, "lines.0.unit_price", "decimal_max_digits", id="money-as-float"
        ),
    ],
)
def test_a_wrong_shape_is_rejected_at_its_field(
    invoice_with: Callable[[dict[str, Any]], dict[str, Any]], changes: dict[str, Any], field: str, error_type: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        Invoice.model_validate(invoice_with(changes))
    assert problems(caught.value) == {(field, error_type)}


def test_every_problem_is_reported_at_once(invoice_data: dict[str, Any]) -> None:
    del invoice_data["vat_total"]
    invoice_data["vat_amount"] = "64.35"  # a typo for vat_total
    with pytest.raises(ValidationError) as caught:
        Invoice.model_validate(invoice_data)
    assert problems(caught.value) == {("vat_total", "missing"), ("vat_amount", "extra_forbidden")}


@pytest.mark.parametrize(
    "printed",
    ["٣٩٩٩٩٩٩٩٩٩٠٠٠١٣", "٣٩٩ ٩٩٩ ٩٩٩٩ ٠٠٠١٣", "399-9999999-00013"],
    ids=["arabic-digits", "arabic-digits-spaced", "dashes"],
)
def test_a_vat_number_is_stored_as_plain_ascii_digits(
    invoice_with: Callable[[dict[str, Any]], dict[str, Any]], printed: str
) -> None:
    invoice = Invoice.model_validate(invoice_with({"seller.vat_number": printed}))
    assert invoice.seller.vat_number == "399999999900013"


def test_a_parsed_invoice_cannot_be_changed(invoice_data: dict[str, Any]) -> None:
    invoice = Invoice.model_validate(invoice_data)
    with pytest.raises(ValidationError, match="Instance is frozen"):
        # mypy already refuses this line (the model is frozen); the test checks Pydantic refuses it at runtime.
        invoice.total = Decimal("1.00")  # type: ignore[misc]
