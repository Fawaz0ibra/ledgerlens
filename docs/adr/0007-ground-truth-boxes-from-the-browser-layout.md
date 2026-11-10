# 0007. Ground truth: one JSON per page, with field boxes from the browser's layout

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

The generator draws each synthetic invoice as a PDF and a PNG ([0006](0006-render-invoices-with-headless-chromium.md)).
Module 4 trains vision models to find each value on the page and read it, and Modules 3 and 6 grade
extractors against the right answers. So each page needs its values, where each one is printed, and the
text as printed ("1,250.00" where the data says 1250.00). The page is bilingual and right to left, and
some values appear twice, once in each language.

## Decision

Next to each page, one JSON file holds the synthetic invoice and its `layout`: one box per printed
value, with the value's path in the same file (`invoice.lines.0.unit_price`), which copy (`ar`, `en`)
for a value printed in both languages, the printed text, and the box in PNG pixels (whole numbers,
rounded outwards) and in PDF points (to 0.01), both measured from the top-left corner. The template marks
each value with `data-field`. The browser measures each box with a DOM Range over the value's text,
from the same layout the screenshot is taken of. A `dataset.json` records the generator version, the
browser, the seed and the count. The generator's version goes up whenever the same seed would give
different files. A test checks that the PDF's own text sits inside the boxes.

## Rejected options

- **The element's own box** (measured): a block element is as wide as its column, so a seller name 128 px
  wide got a 302 px box.
- **Boxes from the PDF's text layer** (measured): the PDF holds Arabic in drawing order, and pdfium reads
  some Arabic words back to front (مؤسسة as ةسسؤم), so its text can't be matched to values directly.
  Asking it for the text inside a rectangle also returns letters from the watermark and from the next
  line. It stays as the independent check, with characters matched by their centre.
- **Ink boxes from the pixels** (not measured): drawing each value alone and comparing images costs an
  extra drawing per value. The layout boxes miss ink by under 1 pt (below).
- **A separate annotation file in COCO or FUNSD format** (not measured): COCO describes object categories,
  not values with text, and a second file can fall out of step with its page. A converter can write
  either format when a Module 4 tool needs it.
- **Word or character boxes** (not measured): no model needs them yet. Module 4 can add them from the same
  Range (its `getClientRects()`), with a new record.

## Measurements

200 invoices (seed 20261109), drawn and checked with the code in the commit that adds this record.

| | Result |
|---|---|
| Boxes per page (min / median / max) | 24 / 40 / 62 |
| Text boxes whose PDF characters (centres inside, watermark left out) match the printed text exactly | 8,166 of 8,166 (the other 200 boxes are QR images) |
| The same check on an earlier template, with the watermark not left out | 426 of 6,139 differ |
| Ink beyond the box, worst case | 0.76 pt left, 0.58 pt below, 0.04 pt above, none right |
| Measuring step per page (median / slowest) | 6.6 / 26.5 ms, within a 233 ms median per page |
| JSON per page (median / largest) | 13.9 / 21.8 kB |
| PDF page size from Chromium | 594.96 x 841.92 pt (A4 is 595.28 x 841.89) |

The watermark is the only rotated text on the page (28 characters per page at 330°), so the check leaves
out rotated characters. Runs on 2026-11-10: WSL2 Ubuntu 24.04 on a Ryzen 5 3600X, Python 3.12.15,
Chromium 156.0.8078.4 through Playwright 1.64.1, pypdfium2 5.14.0.

## Consequences

- A box is the text's layout box: the font's full height and the letters' advance widths. Plex Arabic
  is tall, so boxes on neighbouring lines overlap by a few pixels (7 px on one sample), and ink can stick
  out by up to a CSS pixel. Module 4 should treat boxes as layout boxes, not tight ink boxes.
- Every value the invoice prints gets a box, and so must be in the JSON. The per-line VAT and amount with
  VAT aren't in the contract, so the generator writes them (`line_vat`). A first draft left them unboxed;
  a model would then have learned that some amounts on the page are background. A test lists the
  expected fields.
- The template's own text (headings, labels, row numbers, the marker) has no box. A model that finds
  values doesn't need it; OCR training needs every word boxed, and that is Module 4's decision.
- Paths point into the same file, so a reader needs only one file per page.
- Datasets made by different generator versions can't be compared as the same data; `dataset.json` says
  which made which.

## Revisit when

- A Module 4 model needs word or character boxes, or tight ink boxes.
- A layout change (lesson 1.7's drift) makes the PDF check fail, or adds values printed outside the template.
- Chromium's PDF stops matching the boxes after a Playwright upgrade.
