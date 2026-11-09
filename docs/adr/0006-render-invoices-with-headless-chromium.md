# 0006. Render the synthetic invoices with headless Chromium

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

The invoice generator (lessons 1.6 and 1.7) turns each invoice into the page a person would see, as a
PDF and a PNG. The pages are bilingual: Arabic, right to left and legally binding, with English beside
it. So the renderer has to shape Arabic correctly, letters joined in their right forms, and order mixed
right-to-left and left-to-right text, numbers included. Module 4 trains vision models on these pages,
so the ground truth also needs where each field landed on the page, and the PDF and the PNG must come
from one layout. It runs on this machine and in CI, and the same input must give the same pixels.

## Decision

An HTML template (Jinja2 3.1.6), drawn by Chromium's headless shell 156.0.8078.4 through Playwright
1.64.1. The PNG is a screenshot at twice 96 pixels per inch (1588 x 2246 for A4); the PDF is printed
from the same screen layout. The pages use only the bundled IBM Plex Sans Arabic 1.101, embedded in the
page itself, and rendering stops if a font fails to load. The QR image comes from segno 1.6.6. Only the
headless shell is installed (`playwright install --with-deps --only-shell chromium`).

## Rejected options

- **WeasyPrint 70.0** (measured below): it drew the same Arabic just as correctly, with smaller PDFs and
  no browser to download. But it is three times slower once a PNG is needed, it makes no PNG itself, and
  it has no public way to ask where an element landed, which the ground truth needs.
- **ReportLab** (not measured): no HTML or CSS, so every line is positioned by hand, and Arabic shaping
  and right-to-left ordering need extra libraries on top.
- **wkhtmltopdf** (not measured): its GitHub repository is archived (last change November 2022), and its
  browser engine is years old.
- **LaTeX** (not measured): a large toolchain for one template, and it doesn't report where things landed.
- **Full Chromium** (`playwright install chromium`): 403 MB more on disk, for a browser we never use;
  headless runs use the headless shell.

## Measurements

The same 30 invoices (seed 20261109) drawn by each renderer, with `tools/render-compare/compare.py`.
Times are for PDF and PNG together, after one warm-up page. WeasyPrint's PNG is its PDF drawn by
pypdfium2 5.14.0 at the same resolution.

| | Chromium (chosen) | WeasyPrint |
|---|---|---|
| Time per page, median | 262 ms | 798 ms |
| Time per page, slowest | 319 ms | 1,162 ms |
| PDF size, median | 39 kB | 28 kB |
| PNG size, median | 206 kB | 324 kB |
| Pages per invoice | 1 | 1 |
| Same PNG bytes when drawn twice | yes | yes |
| Same PDF bytes 1.5 s later | no | no |
| Arabic shaping and right-to-left order, by eye (3 pages each) | correct | correct, no visible difference |
| Where each field landed | yes, from the browser's layout | no public API |

Neither PDF repeats byte for byte: both record when the PDF was made. The PNG and the JSON are what the
dataset relies on. Chromium also starts in 0.57 s, once per run. Its headless shell takes 273 MB on disk
(plus 5.1 MB for the ffmpeg Playwright always fetches), and on a fresh WSL Ubuntu 24.04 its system
libraries were 27 packages, 105 MB. In CI (run 42700109041) the browser step takes 16 s, and the checks
job went from 30–33 s to 57 s.

Runs on 2026-11-09: WSL2 Ubuntu 24.04 on a Ryzen 5 3600X, Python 3.12.15, WeasyPrint with the system's
Pango 1.52.1 and HarfBuzz 8.3.0. The code is the commit that adds this record.

## Consequences

- Every machine that draws pages needs the browser and its libraries: a one-time setup locally (in the
  README), and a step in CI.
- Positions come from the same layout that made the pixels, so the ground-truth boxes (next) can't drift
  from the image.
- Playwright's synchronous API allows one browser session per process. The command keeps one open for all
  its pages; the tests that need a second one live in their own file.
- Upgrading Playwright changes the Chromium build, which can move text by a pixel. A dataset records the
  Playwright version that drew it, and comparing datasets across versions needs a re-render.

## Revisit when

- Drawing becomes the bottleneck for a large dataset (at 262 ms a page, 10,000 pages take about 44
  minutes in one tab): first try several tabs, before any other engine.
- A Playwright upgrade changes rendered pixels for the same input.
- The pages need features the headless shell lacks.
