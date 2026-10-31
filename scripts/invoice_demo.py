"""A tour of the invoice contract. Run from the repo root:  uv run scripts/invoice_demo.py

The vendors are fictional and the VAT numbers follow the test-only pattern in data/README.md.
"""

import copy
import json

from pydantic import ValidationError

from ledgerlens.contracts import Invoice, check_invoice

GOOD = {
    "invoice_number": "INV-2026-0001",
    "invoice_type": "standard",
    "issue_date": "2026-10-30",
    "currency": "SAR",
    "seller": {"name_en": "Example Trading Co.", "name_ar": "شركة المثال للتجارة", "vat_number": "399999999900013"},
    "buyer": {"name_en": "Sample Buyer Ltd.", "name_ar": "شركة العينة المحدودة", "vat_number": "399999999900023"},
    "lines": [
        {"description_en": "A4 paper, box of 5 reams", "description_ar": "ورق A4، علبة 5 رزم",
         "quantity": "10", "unit_price": "25.00", "vat_rate": "0.15", "line_total": "250.00"},
        {"description_en": "Ink cartridge", "description_ar": "خرطوشة حبر",
         "quantity": "2", "unit_price": "89.50", "vat_rate": "0.15", "line_total": "179.00"},
    ],
    "subtotal": "429.00",
    "vat_total": "64.35",
    "total": "493.35",
}


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    section("1. A good invoice, arriving as JSON")
    invoice = Invoice.model_validate_json(json.dumps(GOOD))
    print(f"seller: {invoice.seller.name_en} / {invoice.seller.name_ar}")
    print(f"total: {invoice.total!r}")
    print(f"findings: {check_invoice(invoice)}")

    section("2. Wrong shape: four problems at once")
    bad = copy.deepcopy(GOOD)
    bad["seller"]["vat_number"] = "39999999990001"  # 14 digits
    bad["issue_date"] = "30/10/2026"  # dates must be ISO: 2026-10-30
    bad["lines"][1] = {k: v for k, v in bad["lines"][1].items() if not k.startswith("description")}
    bad["discount"] = "5.00"  # not a field in the contract
    try:
        Invoice.model_validate_json(json.dumps(bad))
    except ValidationError as err:
        for e in err.errors():
            print(f"{'.'.join(map(str, e['loc'])):<30} {e['msg']}")

    section("3. A VAT number printed in Arabic digits")
    arabic = copy.deepcopy(GOOD)
    arabic["seller"]["vat_number"] = "٣٩٩٩٩٩٩٩٩٩٠٠٠١٣"
    print(f"stored as: {Invoice.model_validate_json(json.dumps(arabic)).seller.vat_number}")

    section("4. Right shape, wrong numbers: VAT inflated by 5.65")
    inflated = copy.deepcopy(GOOD)
    inflated["vat_total"], inflated["total"] = "70.00", "499.00"
    for finding in check_invoice(Invoice.model_validate_json(json.dumps(inflated))):
        print(f"{finding.code}: {finding.message}")

    section("5. The same contract as JSON Schema, for an LLM or another language")
    schema = Invoice.model_json_schema()
    print(f"required: {schema['required']}")
    print(f"VAT number rule: {schema['$defs']['Party']['properties']['vat_number']['anyOf'][0]['pattern']}")


if __name__ == "__main__":
    main()
