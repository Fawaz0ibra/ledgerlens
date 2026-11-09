"""The ZATCA QR payload: tags 1 to 5, each as tag, length, value; then Base64."""

import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ledgerlens_datagen.qr import MAX_VALUE_BYTES, QrFields, decode, encode

RIYADH = timezone(timedelta(hours=3))
SELLER_AR = "شركة سحاب للطباعة"


def _fields(seller_name: str = "Sahab Printing Co.", issued_at: datetime | None = None) -> QrFields:
    return QrFields(
        seller_name=seller_name,
        vat_number="399999999900013",
        issued_at=issued_at or datetime(2026, 3, 14, 13, 5, 9, tzinfo=RIYADH),
        total=Decimal("1150.00"),
        vat_total=Decimal("150.00"),
    )


def test_the_bytes_match_the_standard_written_out_by_hand() -> None:
    # Tag byte, length byte, value: as ZATCA's section 4 describes, written out without using encode().
    expected = (
        b"\x01\x12Sahab Printing Co."
        b"\x02\x0f399999999900013"
        b"\x03\x142026-03-14T10:05:09Z"  # 13:05:09 in Riyadh is 10:05:09 UTC
        b"\x04\x071150.00"
        b"\x05\x06150.00"
    )
    assert base64.b64decode(encode(_fields())) == expected


def test_the_length_counts_utf8_bytes_not_characters() -> None:
    tag, length = base64.b64decode(encode(_fields(SELLER_AR)))[:2]
    # 15 Arabic letters at 2 bytes each, plus 2 spaces at 1 byte: 17 characters, 32 bytes.
    assert len(SELLER_AR) == 17
    assert (tag, length) == (1, 32)


def test_a_value_over_255_bytes_is_refused() -> None:
    encode(_fields("a" * MAX_VALUE_BYTES))  # exactly 255 still fits
    with pytest.raises(ValueError, match="tag 1 is 256 bytes"):
        encode(_fields("a" * (MAX_VALUE_BYTES + 1)))


def test_the_longest_possible_code_fits_zatcas_700_characters() -> None:
    # The longest seller name one length byte allows, and the largest amounts the contract allows
    # (15 digits, 2 after the point). So encode() never needs its own 700-character check.
    longest = QrFields(
        seller_name="a" * MAX_VALUE_BYTES,
        vat_number="399999999900013",
        issued_at=datetime(2026, 3, 14, 13, 5, 9, tzinfo=RIYADH),
        total=Decimal("9999999999999.99"),
        vat_total=Decimal("9999999999999.99"),
    )
    assert len(encode(longest)) <= 700


def test_a_time_without_a_time_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        encode(_fields(issued_at=datetime(2026, 3, 14, 13, 5, 9)))


def test_decode_gives_back_every_field() -> None:
    fields = decode(encode(_fields(SELLER_AR)))
    assert {tag: value.decode("utf-8") for tag, value in fields.items()} == {
        1: SELLER_AR,
        2: "399999999900013",
        3: "2026-03-14T10:05:09Z",
        4: "1150.00",
        5: "150.00",
    }


@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(b"\x01\x05abc", "tag 1 says 5 bytes but only 3 follow", id="value-cut-short"),
        pytest.param(b"\x01\x01a\x02", "ends inside a tag and length", id="header-cut-short"),
    ],
)
def test_decode_refuses_broken_tlv(data: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        decode(base64.b64encode(data).decode("ascii"))


def test_decode_refuses_text_that_isnt_base64() -> None:
    with pytest.raises(ValueError, match="Only base64 data is allowed"):
        decode("not base64!")
