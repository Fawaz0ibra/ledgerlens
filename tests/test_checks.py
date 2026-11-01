"""check_invoice compares the stated numbers. Each kind of wrong number gives its own finding, and only that one."""

from typing import Any

import pytest

from ledgerlens.contracts import Invoice, check_invoice


def finding_codes(data: dict[str, Any]) -> list[str]:
    return [finding.code for finding in check_invoice(Invoice.model_validate(data))]


def test_a_correct_invoice_has_no_findings(invoice_data):
    assert finding_codes(invoice_data) == []


@pytest.mark.parametrize(("changes", "expected"), [
    # 10 x 26.00 is 260.00, but the line still says 250.00.
    pytest.param({"lines.0.unit_price": "26.00"}, ["line_total_mismatch"], id="line-total"),
    # 5% isn't a Saudi rate. The totals are worked out at 5%, so the rate is the only thing wrong.
    pytest.param({"lines.1.vat_rate": "0.05", "vat_total": "46.45", "total": "475.45"}, ["unexpected_vat_rate"],
                 id="vat-rate"),
    pytest.param({"subtotal": "430.00", "total": "494.35"}, ["subtotal_mismatch"], id="subtotal"),
    pytest.param({"vat_total": "70.00", "total": "499.00"}, ["vat_total_mismatch"], id="inflated-vat"),
    pytest.param({"total": "500.00"}, ["total_mismatch"], id="total"),
    pytest.param({"seller.vat_number": None}, ["seller_vat_missing"], id="no-seller-vat"),
])
def test_each_wrong_number_gives_only_its_own_finding(invoice_with, changes, expected):
    assert finding_codes(invoice_with(changes)) == expected


# The correct VAT is 64.35. One halala either way is allowed for rounding; two is a finding.
@pytest.mark.parametrize(("vat_total", "total", "expected"), [
    pytest.param("64.36", "493.36", [], id="one-halala-over"),
    pytest.param("64.34", "493.34", [], id="one-halala-under"),
    pytest.param("64.37", "493.37", ["vat_total_mismatch"], id="two-halalas-over"),
    pytest.param("64.33", "493.33", ["vat_total_mismatch"], id="two-halalas-under"),
])
def test_vat_may_be_off_by_one_halala_for_rounding(invoice_with, vat_total, total, expected):
    assert finding_codes(invoice_with({"vat_total": vat_total, "total": total})) == expected
