"""Arithmetic and tax checks on an invoice that already has the right shape.

Each check returns findings instead of raising: a wrong total is a result to report, not a crash.
Each check compares stated numbers with each other, so one wrong line doesn't cascade into a
finding on every total below it.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ledgerlens.contracts.invoice import Invoice

SAUDI_VAT_RATES = frozenset({Decimal("0.15"), Decimal("0")})
HALALA = Decimal("0.01")
# Rounding VAT per line or once on the total can differ by one halala; both are common.
VAT_TOLERANCE = HALALA


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(HALALA, rounding=ROUND_HALF_UP)


def check_invoice(invoice: Invoice) -> list[Finding]:
    findings: list[Finding] = []

    if invoice.seller.vat_number is None:
        findings.append(Finding("seller_vat_missing", "The seller has no VAT number."))

    for n, line in enumerate(invoice.lines, start=1):
        expected = _round(line.quantity * line.unit_price)
        if line.line_total != expected:
            findings.append(Finding("line_total_mismatch",
                                    f"Line {n}: {line.quantity} x {line.unit_price} = {expected}, "
                                    f"but the line total says {line.line_total}."))
        if line.vat_rate not in SAUDI_VAT_RATES:
            findings.append(Finding("unexpected_vat_rate",
                                    f"Line {n}: VAT rate {line.vat_rate * 100:.2f}% is not a Saudi rate (15% or 0%)."))

    lines_sum = sum((line.line_total for line in invoice.lines), Decimal("0"))
    if invoice.subtotal != lines_sum:
        findings.append(Finding("subtotal_mismatch",
                                f"The lines add up to {lines_sum}, but the subtotal says {invoice.subtotal}."))

    expected_vat = _round(sum((line.line_total * line.vat_rate for line in invoice.lines), Decimal("0")))
    if abs(invoice.vat_total - expected_vat) > VAT_TOLERANCE:
        findings.append(Finding("vat_total_mismatch",
                                f"VAT on these lines is {expected_vat}, but the VAT total says {invoice.vat_total}."))

    if invoice.total != invoice.subtotal + invoice.vat_total:
        findings.append(Finding("total_mismatch",
                                f"{invoice.subtotal} + {invoice.vat_total} = {invoice.subtotal + invoice.vat_total}, "
                                f"but the total says {invoice.total}."))

    return findings
