# Dataset card: LedgerLens synthetic invoices

Bilingual Arabic/English invoices in the style ZATCA (the Saudi tax authority) requires, drawn as pages
with the right answers next to them. LedgerLens tests and trains on them instead of real invoices. They
are made on demand by this package's command and never committed; [data/README.md](../data/README.md)
holds the data policy.

| | |
|---|---|
| Generator | `ledgerlens-datagen` 0.2.0 (this folder) |
| One invoice | A one-page A4 PNG (1588 x 2246, 192 pixels per inch), the same page as a PDF, and its ground truth as JSON |
| Languages | Arabic and English on every page; Arabic is the binding text on a real invoice |
| Kinds | Standard tax invoices, to businesses (about 70%), and simplified ones, to consumers |
| Labels | Every value on the page, its path in the JSON, the text as printed, and its box ([ADR 0007](../docs/adr/0007-ground-truth-boxes-from-the-browser-layout.md)) |
| Licence | Apache-2.0, like the code. The PDFs embed IBM Plex Sans Arabic, under the SIL Open Font License 1.1 ([fonts](src/ledgerlens_datagen/fonts/README.md)) |
| Use | Testing and training LedgerLens. **Not** for tax filing, and not to be shown as a real invoice |

## Making it

```bash
uv run ledgerlens-datagen --seed 7 --count 100 --out data/invoices-seed7
uv run python tools/box-overlay/overlay.py data/invoices-seed7   # optional: the boxes drawn over each page
```

Invoice *n* depends only on the seed and *n*, so it is the same in a set of 10 or 10,000. `dataset.json`
records the generator version, the browser, the seed and the count. Two runs with the same record write
identical JSON and PNG files; the PDFs differ, because each records when it was made. The generator's
version goes up whenever the same seed would give different files.

## Files

| File | Holds |
|---|---|
| `NNNNN.png` | The page as an image |
| `NNNNN.pdf` | The same page as a PDF, with a text layer |
| `NNNNN.json` | The ground truth: `seed`, `index`, `invoice` (a LedgerLens contract invoice), `issued_at`, `seller_address`, `buyer_address`, `qr_code` (the text inside the QR code), `line_vat` (each line's VAT and amount with VAT) and `layout` |
| `dataset.json` | What made the folder |

## The ground truth

`layout.fields` has one entry per value printed on the page, 24 to 62 per page. One, from seed 7's first
invoice:

```json
{"field": "invoice.total", "lang": null, "text": "11,361.47", "png": [366, 1358, 481, 1395], "pdf": [137.36, 509.57, 180.11, 523.07]}
```

- `field` is the value's path in the same file; list items are numbered from 0 (`invoice.lines.0.unit_price`).
- `lang` is `ar` or `en` for a value printed in both languages (the title, the addresses, the buyer's VAT
  number, the currency), and `null` otherwise.
- `text` is the value as printed, which often differs from the JSON: `11,361.47` for `11361.47`,
  `31/03/2026` for `2026-03-31`, `15%` for `0.15`, `Tax Invoice` for `standard`. It is `null` for the QR code.
- `png` and `pdf` are the same box, `[left, top, right, bottom]`, from the page's top-left corner with y
  growing downwards: whole PNG pixels, rounded outwards, and PDF points to 0.01. A PDF counts from the
  bottom-left corner, so a PDF tool may need the y values flipped. The PDF page is 594.96 x 841.92 points.

The boxes come from the browser's layout of the text, not from the ink: they are the font's full height,
so boxes on neighbouring lines can overlap by a few pixels, and a letter can stick out by up to a CSS
pixel (0.76 pt, measured on 200 pages). The tests check, page by page, that the PDF's own text sits in
each box.

Every value of the invoice has a box. The template's own text doesn't: the headings and labels ("VAT
amount", "Invoice number"), the row numbers, the currency note and the marker. They tell a reader what
a value means, but they aren't values. A model trained to find text of every kind, such as an OCR
detector, would need boxes for them too.

## How the invoices are made

- **Companies:** 40 fictional companies per seed, in 7 trades, with names built from word lists and
  addresses in 6 Saudi cities (4-digit building numbers, 5-digit postal codes). Each company both sells
  and buys.
- **Invoices:** a seller, and for a standard invoice another company as the buyer. Lines come from a
  bilingual catalogue of 5 items per trade (35 in all), each item at most once: 1 to 5 lines on a standard
  invoice, 1 to 3 on a simplified one. Dates are 1 January to 31 October 2026, times 08:00 to 21:59 Riyadh
  time (UTC+3).
- **Amounts:** exact decimals, 15% VAT on the subtotal, rounded to the halala (half up). Each line also
  has its own VAT, rounded per line (`line_vat`), as ZATCA asks for on a tax invoice. Added up, the lines'
  VAT can miss the VAT total by a halala or two, as on real invoices: over 2,000 invoices it matched in
  1,763, was one halala off in 236 and two halalas off in 1.
- **All clean:** every invoice passes LedgerLens's own checks with no findings. Lesson 1.7 adds labelled
  anomalies and layout drift.

## ZATCA rules followed

| Rule | Source |
|---|---|
| Two kinds, titled "Tax Invoice" / فاتورة ضريبية and "Simplified Tax Invoice" / فاتورة ضريبية مبسطة; a standard invoice names the buyer with address and VAT number | Guideline for Tax Invoicing and Records under VAT Provisions, version 3 (May 2026), §4.1 to §4.3 |
| Arabic on every invoice; dates in numerals go day/month/year; VAT in SAR to the halala | The same guideline |
| A VAT number is 15 digits, starting and ending with 3 (BR-KSA-40) | Electronic Invoice XML Implementation Standard, version 1.2 (2023-05-19) |
| Every invoice carries a QR code (BR-KSA-27; on standard invoices since January 2023, guideline §4.2.3) | The XML standard and the guideline |
| The QR code holds tag-length-value fields as UTF-8 bytes, in Base64, at most 700 characters: seller name, VAT number, time stamp, total with VAT, VAT total (tags 1 to 5) | E-invoicing Detailed Technical Guidelines, version 2 (November 2022); Electronic Invoice Security Features Implementation Standards (2023-05-19) |

ZATCA's own worked examples contain arithmetic slips, so the generator follows the rules, not the examples.

## What makes them not real

- **A marker:** "SYNTHETIC SAMPLE FOR TESTING — NOT A TAX INVOICE", in Arabic and English, at the top and
  bottom of every page, and a watermark across the middle.
- **No cryptographic stamp:** a real e-invoice's QR code also holds tags 6 to 9 (the invoice's hash, its
  signature, the public key and ZATCA's signature on it), made with a ZATCA-issued certificate. Ours
  carry tags 1 to 5 only; fake stamps would make the pages look more real.
- **No XML:** a real e-invoice is an XML file sent to ZATCA; these are pages only.
- **Fictional companies:** names are built from word lists with brand names left out. A match with a real
  business would be a coincidence.
- **Test-pattern VAT numbers,** below.

## VAT numbers

Every VAT number is `3999999999`, a 4-digit serial, then `3`; companies get serials from 0001 up. The
pattern comes from ZATCA's SDK (the Compliance and Enablement Toolbox, release R3.4.8), whose samples use
399999999900003 for a seller and 399999999910003 for a VAT group: serials 0000 and 1000, which our
companies never get. The numbers pass BR-KSA-40 like real ones. We found no ZATCA statement that
reserves the whole range for tests, so the claim rests on the pattern ZATCA's own samples use. ZATCA's
documents also show VAT numbers that may belong to real companies; none of those are used here.

## Limits

- One layout. Lesson 1.7 adds layout drift.
- Western digits (123) only, though ZATCA also allows Arabic-Indic digits (١٢٣).
- No discounts, no zero-rated or exempt lines, one currency (SAR), one page.
- The PDF's text layer holds Arabic in drawing order, and some PDF readers return Arabic words back to
  front. Read text from `text` in the JSON, not from the PDF.
- Drawn by Chromium 156.0.8078.4 through Playwright 1.64.1; another browser version can move text by a
  pixel ([ADR 0006](../docs/adr/0006-render-invoices-with-headless-chromium.md)).
