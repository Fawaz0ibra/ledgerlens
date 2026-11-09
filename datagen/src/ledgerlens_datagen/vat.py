"""VAT numbers for synthetic invoices, from a test-only range: never a number a real taxpayer could hold.

ZATCA's own SDK (R3.4.8) uses 399999999900003 for its sample seller and 399999999910003 for its sample
VAT group. We extend that pattern: 3999999999, then a 4-digit serial, then 3. That is 15 digits starting
and ending with 3 (ZATCA rule BR-KSA-40), so it passes the same format check as a real number, and the
run of nine 9s after the first 3 marks it as a test number. Serials 0000 and 1000 are ZATCA's two numbers.
"""

import re

PREFIX = "3999999999"
SUFFIX = "3"
MAX_SERIAL = 9999

_TEST_NUMBER = re.compile(rf"{PREFIX}[0-9]{{4}}{SUFFIX}")


def vat_number_for(serial: int) -> str:
    """The test VAT number for a fictional company's serial, 0 to 9999."""
    if not 0 <= serial <= MAX_SERIAL:
        raise ValueError(f"serial must be 0 to {MAX_SERIAL}, got {serial}")
    return f"{PREFIX}{serial:04d}{SUFFIX}"


def is_test_vat_number(number: str) -> bool:
    return _TEST_NUMBER.fullmatch(number) is not None
