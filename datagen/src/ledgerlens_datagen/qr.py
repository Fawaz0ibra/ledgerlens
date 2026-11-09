"""The QR code ZATCA requires on every tax invoice: fields 1 to 5, TLV-encoded, then Base64.

The rules are from ZATCA's Security Features Implementation Standards v1.2 (2023-05-19), section 4. Each
field is one byte of tag, one byte of length, then the value as UTF-8, with nothing between fields; the
bytes are then written as Base64. The length counts bytes, not characters: an Arabic letter is 2 bytes.

Tags 6 to 9 (the XML invoice's hash, its signature, the public key, and ZATCA's signature on that key) need
a certificate that ZATCA issues to a registered invoicing device. We have none, and fake ones would make
synthetic invoices look more like real ones, so our codes carry tags 1 to 5 only.
"""

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

# The length is stored in one byte, so no value can be longer than this.
MAX_VALUE_BYTES = 255


@dataclass(frozen=True)
class QrFields:
    """Tags 1 to 5, in tag order."""

    seller_name: str
    vat_number: str
    issued_at: datetime  # must carry its time zone; the code holds it in UTC
    total: Decimal  # including VAT
    vat_total: Decimal

    def values(self) -> tuple[str, str, str, str, str]:
        if self.issued_at.tzinfo is None:
            raise ValueError("issued_at needs a time zone, or the time in the QR code would be ambiguous")
        timestamp = self.issued_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.seller_name, self.vat_number, timestamp, f"{self.total:.2f}", f"{self.vat_total:.2f}"


def encode(fields: QrFields) -> str:
    """The text the QR code holds."""
    payload = bytearray()
    for tag, value in enumerate(fields.values(), start=1):
        data = value.encode("utf-8")
        if len(data) > MAX_VALUE_BYTES:
            raise ValueError(f"tag {tag} is {len(data)} bytes in UTF-8; a QR field holds at most {MAX_VALUE_BYTES}")
        payload += bytes((tag, len(data))) + data
    return base64.b64encode(payload).decode("ascii")


def decode(text: str) -> dict[int, bytes]:
    """Split QR text back into {tag: value bytes}. Raises ValueError if it isn't Base64-encoded TLV."""
    data = base64.b64decode(text, validate=True)
    fields: dict[int, bytes] = {}
    position = 0
    while position < len(data):
        if position + 2 > len(data):
            raise ValueError(f"the data ends inside a tag and length, at byte {position}")
        tag, length = data[position], data[position + 1]
        value = data[position + 2 : position + 2 + length]
        if len(value) < length:
            raise ValueError(f"tag {tag} says {length} bytes but only {len(value)} follow")
        fields[tag] = value
        position += 2 + length
    return fields
