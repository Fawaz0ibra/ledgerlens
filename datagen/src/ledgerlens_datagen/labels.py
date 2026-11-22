"""What the ground truth says about an invoice beyond its values: the anomaly it carries, if any, and the page
design that drew it."""

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

# Each type breaks exactly one rule a reviewer checks; datagen/tests/test_anomalies.py holds those rules.
AnomalyType = Literal[
    "duplicate_exact",  # the same invoice sent again: the same number and everything else
    "duplicate_near",  # the same bill sent again a few days later, under a new number
    "price_above_agreed",  # one line's unit price is above the price on the purchase order
    "quantity_above_ordered",  # one line bills more than the purchase order ordered
    "vat_wrong",  # the VAT total leaves out one line's VAT
    "total_inflated",  # the total is more than the total excluding VAT plus the VAT
    "qr_mismatch",  # the QR code holds the total without VAT, not the total the page prints
]
ANOMALY_TYPES: tuple[AnomalyType, ...] = get_args(AnomalyType)

# "a" is the original page; "b" is the design some vendors switch to once drift starts.
Design = Literal["a", "b"]


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: AnomalyType
    # Where to look: paths into the same JSON, the same paths the page's boxes carry (layout.fields).
    fields: tuple[str, ...]
    duplicate_of: int | None = None  # for a duplicate, the index of the invoice it repeats
