"""Test-only VAT numbers. A number outside this scheme could belong to a real taxpayer."""

import pytest

from ledgerlens.contracts.invoice import Party
from ledgerlens_datagen.vat import MAX_SERIAL, is_test_vat_number, vat_number_for


def test_serials_0000_and_1000_are_zatcas_own_sdk_numbers() -> None:
    # ZATCA's SDK R3.4.8: the sample seller, and the sample VAT group.
    assert vat_number_for(0) == "399999999900003"
    assert vat_number_for(1000) == "399999999910003"


@pytest.mark.parametrize("serial", [0, 1, 4242, MAX_SERIAL])
def test_every_number_passes_the_contract_and_is_in_the_scheme(serial: int) -> None:
    number = vat_number_for(serial)
    assert Party(name_en="Test", vat_number=number).vat_number == number
    assert is_test_vat_number(number)


@pytest.mark.parametrize("serial", [-1, MAX_SERIAL + 1])
def test_serials_outside_the_range_are_refused(serial: int) -> None:
    with pytest.raises(ValueError, match="serial must be 0 to 9999"):
        vat_number_for(serial)


@pytest.mark.parametrize(
    "number",
    [
        pytest.param("399999999800003", id="zatca-sdk-buyer-number-outside-our-range"),
        pytest.param("399999999900004", id="last-digit-not-3"),
        pytest.param("39999999990003", id="14-digits"),
        pytest.param("3999999999000033", id="16-digits"),
    ],
)
def test_other_numbers_are_not_test_numbers(number: str) -> None:
    assert not is_test_vat_number(number)
