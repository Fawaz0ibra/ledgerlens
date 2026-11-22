# 0008. Labelled anomalies and controlled drift in the synthetic invoices

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

LedgerLens exists to flag wrong invoices, so its review agents (Module 5), quality gates (Module 6) and
drift monitoring (Module 10) need invoices whose problems are known exactly. A problem only shows against
something, so the generator first gained the buyer's records: each company's vendor master, its agreed
prices, and the purchase order behind every standard invoice (generator 0.3.0, `purchasing.py`).

## Decision

- **Seven anomaly types, at most one per invoice,** each breaking exactly one rule a reviewer with the
  buyer's records would check: `duplicate_exact` (a repeated number), `duplicate_near` (the same order billed
  again under a new number), `price_above_agreed` and `quantity_above_ordered` (against the order),
  `vat_wrong` and `total_inflated` (`check_invoice`'s own findings), `qr_mismatch` (the decoded QR code
  against the page). Everything else on the page stays consistent with the change.
- **The label** names the type, the fields to look at (the same paths as the page's boxes) and, for a
  duplicate, the invoice it repeats.
- **Anomalies are drawn from their own random stream,** so the clean invoices never change: invoice n
  without an anomaly is exactly the clean invoice n.
- **The rate is a setting:** 5% by default, evenly among the types an invoice can have, with
  `--anomalies` to restrict the types (for an evaluation set of one type).
- **Drift starts on a chosen issue date:** 30% of vendors switch to a second page design (b), and
  anomalies come twice as often. That is a shift in the inputs and a shift in the labels, each known to
  the day.
- `dataset.json` records the settings.

## Rejected options

- **Several anomalies on one invoice:** an evaluation couldn't tell which mistake a model caught.
- **Drawing anomalies from the invoice's own random stream:** every setting change would reshuffle the
  clean invoices too.
- **A currency change as the drift** (in the original plan): it needs ZATCA's rules for invoices in other
  currencies and new contract fields, and it gives a model no new kind of shift beyond the layout change.
  Dropped on 2026-11-22 at the learner's request to keep the lesson on AI-engineering work.
- **Labels in a separate file:** the label sits in the invoice's own JSON, like its boxes, so it can't fall
  out of step with the page.

## Measurements

Seed 20261109, generator 0.3.0, on WSL2 Ubuntu 24.04 (Ryzen 5 3600X), Python 3.12.15, 2026-11-22. The code
is the commit that adds this record.

| | Result |
|---|---|
| 1,000 invoices at a 30% rate: every invoice breaks exactly the rule its label names, clean ones none | 1,000 of 1,000 |
| Hypothesis: random seeds and indexes, clean and with each anomaly forced | 100 + 150 examples, all pass |
| 2,000 invoices at the default 5% | 107 anomalous: 8 to 23 per type |
| Making 2,000 invoices (no drawing): clean / labelled at 5% | 0.24 s / 0.44 s |
| Drift from 2026-07-01, 2,000 invoices | 5.8% anomalous before, 10.0% after; 206 of 837 later invoices in design b |
| Clean invoices repeating an earlier bill's lines and total under a new order (recurring bills) | 2 of 1,000 |

The first duplicate rule compared lines and totals only, and flagged one of those recurring bills (a
monthly cleaning contract) as a duplicate. A bill sent twice repeats its purchase order too; the rule now
checks that.

## Consequences

- At 5% spread over seven types, a 2,000-invoice set holds 8 to 23 of each: too few to measure recall per
  type. Evaluation sets raise the rate or pick one type; monitoring sets keep the low rate. A detector's
  precision has to be quoted at the real rate: with 95% recall and 2% false alarms, it is 0.95 at a 30%
  rate but 0.25 at one type's 0.7%.
- The rules in `datagen/tests/test_anomalies.py` are the baseline Module 5's agents must beat.
- Design b moves every value, and the box tests (ADR 0007) now run on both designs.

## Revisit when

- Module 5 or 6 needs anomalies these rules can't express (an unknown vendor, a changed bank account),
  or several per invoice.
- Module 10 needs a gradual drift rather than a switch on one date.
