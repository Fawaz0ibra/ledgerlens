"""The generator: every invoice is valid and adds up, follows ZATCA's rules, uses only test VAT numbers,
and comes out exactly the same every time."""

import os
import re
import subprocess
import sys
from datetime import UTC, timedelta
from decimal import Decimal

import pytest

from ledgerlens.contracts.checks import check_invoice
from ledgerlens_datagen import qr
from ledgerlens_datagen.cli import main
from ledgerlens_datagen.generate import SyntheticInvoice, generate
from ledgerlens_datagen.vat import is_test_vat_number
from ledgerlens_datagen.world import build_world

SEED = 20261109
INVOICES = list(generate(SEED, 500))

# Anything shaped like a Saudi VAT number: 15 digits, starting and ending with 3, not inside a longer number.
_VAT_SHAPED = re.compile(r"(?<![0-9])3[0-9]{13}3(?![0-9])")


def test_every_invoice_adds_up() -> None:
    for synthetic in INVOICES:
        assert check_invoice(synthetic.invoice) == [], synthetic.invoice.invoice_number


def test_both_kinds_appear_and_follow_zatcas_rules() -> None:
    assert {s.invoice.invoice_type for s in INVOICES} == {"standard", "simplified"}
    for s in INVOICES:
        invoice = s.invoice
        assert invoice.currency == "SAR"
        assert all(line.vat_rate == Decimal("0.15") for line in invoice.lines)
        if invoice.invoice_type == "standard":
            # A tax invoice names the buyer, with its VAT number and address.
            assert invoice.buyer is not None
            assert invoice.buyer.vat_number is not None
            assert invoice.buyer.vat_number != invoice.seller.vat_number
            assert s.buyer_address is not None
        else:
            assert invoice.buyer is None
            assert s.buyer_address is None


def test_every_amount_is_written_to_the_halala() -> None:
    # The ground truth writes money as the page prints it: 122.00, not 122.
    for s in INVOICES:
        invoice = s.invoice
        amounts = [invoice.subtotal, invoice.vat_total, invoice.total]
        amounts += [amount for line in invoice.lines for amount in (line.unit_price, line.line_total)]
        assert all(amount.as_tuple().exponent == -2 for amount in amounts), invoice.invoice_number


def test_no_vat_number_outside_the_test_scheme_appears_anywhere() -> None:
    # The guard for "never a real taxpayer's number": scan everything the generator writes, not just the
    # VAT fields, so a number that slips into a description or an address is caught too.
    for s in INVOICES:
        for number in _VAT_SHAPED.findall(s.model_dump_json()):
            assert is_test_vat_number(number), (s.invoice.invoice_number, number)
        assert s.invoice.seller.vat_number is not None
        assert is_test_vat_number(s.invoice.seller.vat_number)


def test_the_qr_code_holds_the_invoices_own_values() -> None:
    for s in INVOICES:
        fields = {tag: value.decode("utf-8") for tag, value in qr.decode(s.qr_code).items()}
        assert fields == {
            1: s.invoice.seller.name_ar,
            2: s.invoice.seller.vat_number,
            3: s.issued_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            4: f"{s.invoice.total:.2f}",
            5: f"{s.invoice.vat_total:.2f}",
        }


def test_the_issue_time_is_riyadh_time_on_the_issue_date() -> None:
    for s in INVOICES:
        assert s.issued_at.utcoffset() == timedelta(hours=3)
        assert s.issued_at.date() == s.invoice.issue_date


def test_invoice_numbers_are_unique() -> None:
    numbers = [s.invoice.invoice_number for s in INVOICES]
    assert len(set(numbers)) == len(numbers)


def test_the_world_has_unique_companies_with_valid_addresses() -> None:
    companies = build_world(SEED).companies
    for field in ("name_en", "name_ar", "vat_number"):
        assert len({getattr(c, field) for c in companies}) == len(companies), field
    for c in companies:
        assert re.fullmatch(r"[0-9]{4}", c.address.building_number)
        assert re.fullmatch(r"[0-9]{5}", c.address.postal_code)


def test_the_same_seed_gives_the_same_invoices() -> None:
    # Also shows that invoice n doesn't depend on how many are made: 50 here, 500 above.
    assert list(generate(SEED, 50)) == INVOICES[:50]


def test_a_different_seed_gives_different_invoices() -> None:
    other = [s.invoice for s in generate(SEED + 1, 50)]
    assert all(a != b for a, b in zip(other, (s.invoice for s in INVOICES[:50]), strict=True))


def test_the_output_is_byte_identical_in_new_processes_with_different_hash_seeds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Python randomises str hashing in each new process (PYTHONHASHSEED), which changes the order of sets.
    # If the generator ever depended on that order, two processes would print different invoices.
    code = "from ledgerlens_datagen.cli import main; main(['--seed', '7', '--count', '30'])"
    outputs = [
        subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            check=True,
        ).stdout
        for hash_seed in ("1", "2")
    ]
    main(["--seed", "7", "--count", "30"])
    assert outputs[0] == outputs[1] == capsys.readouterr().out.encode("utf-8")


def test_the_command_prints_one_json_invoice_per_line_and_nothing_is_lost(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--seed", str(SEED), "--count", "3"])
    lines = capsys.readouterr().out.splitlines()
    # Reading the JSON back gives exactly the same invoices: amounts, dates and Arabic text all survive.
    assert [SyntheticInvoice.model_validate_json(line) for line in lines] == INVOICES[:3]
