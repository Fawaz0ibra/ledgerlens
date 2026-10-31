"""A tour of the invoice contract. Run from the repo root:  uv run scripts/invoice_demo.py

The sample invoice is scripts/sample_invoice.json. Its vendors are fictional and its VAT numbers follow
the test-only pattern in data/README.md.
"""

import copy
import json
from pathlib import Path

from pydantic import ValidationError

from ledgerlens.contracts import Invoice, check_invoice

GOOD = json.loads(Path(__file__).with_name("sample_invoice.json").read_text(encoding="utf-8"))


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
