"""Measure the two rendering candidates for ADR 0006 on the same invoice pages.

Run from the repo root, after `uv run playwright install chromium`:

    uv run --with weasyprint==70.0 --with pillow==13.0.0 python tools/render-compare/compare.py

Chromium (through Playwright) draws the PDF and the PNG from one layout. WeasyPrint draws only a PDF,
so its PNG comes from drawing that PDF with pypdfium2 at the same 192 pixels per inch. The first three
pages from each are written to data/render-compare/ (git-ignored), to compare by eye.
"""

import io
import statistics
import time
from collections.abc import Callable
from pathlib import Path

import pypdfium2 as pdfium
from weasyprint import HTML

from ledgerlens_datagen.generate import generate
from ledgerlens_datagen.render import PNG_SCALE, open_renderer, render_html

SEED = 20261109
COUNT = 30
OUT = Path("data/render-compare")


def weasyprint_page(html: str) -> tuple[bytes, bytes]:
    pdf = HTML(string=html).write_pdf()
    document = pdfium.PdfDocument(pdf)
    try:
        image = document[0].render(scale=96 * PNG_SCALE / 72).to_pil()
    finally:
        document.close()
    png = io.BytesIO()
    image.save(png, format="PNG")
    return pdf, png.getvalue()


def page_count(pdf: bytes) -> int:
    document = pdfium.PdfDocument(pdf)
    try:
        return len(document)
    finally:
        document.close()


def measure(name: str, draw: Callable[[str], tuple[bytes, bytes]]) -> dict[str, object]:
    invoices = list(generate(SEED, COUNT))
    pages = [render_html(s) for s in invoices]
    draw(pages[0])  # warm-up: the first page pays one-off costs (font decoding, caches)
    seconds, pdf_sizes, png_sizes, page_counts = [], [], [], []
    for index, html in enumerate(pages):
        start = time.perf_counter()
        pdf, png = draw(html)
        seconds.append(time.perf_counter() - start)
        pdf_sizes.append(len(pdf))
        png_sizes.append(len(png))
        page_counts.append(page_count(pdf))
        if index < 3:
            (OUT / f"{name}-{index}.png").write_bytes(png)
    first_pdf, first_png = draw(pages[0])
    time.sleep(1.5)  # cross a clock second: a PDF that records when it was made will then differ
    again_pdf, again_png = draw(pages[0])
    return {
        "renderer": name,
        "ms per page (median)": round(statistics.median(seconds) * 1000),
        "ms per page (slowest)": round(max(seconds) * 1000),
        "PDF kB (median)": round(statistics.median(pdf_sizes) / 1000),
        "PNG kB (median)": round(statistics.median(png_sizes) / 1000),
        "pages per invoice": sorted(set(page_counts)),
        "same PDF bytes twice": again_pdf == first_pdf,
        "same PNG bytes twice": again_png == first_png,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with open_renderer() as renderer:
        startup = time.perf_counter() - start

        def chromium_page(html: str) -> tuple[bytes, bytes]:
            page = renderer.draw(html)
            return page.pdf, page.png

        results = [measure("chromium", chromium_page)]
    results.append(measure("weasyprint", weasyprint_page))
    print(f"Chromium start-up: {startup:.2f} s (once per run)")
    for key in results[0]:
        print(f"{key:<24}" + "".join(f"{result[key]!s:>14}" for result in results))
    print(f"\nSample pages: {OUT.resolve()}")


if __name__ == "__main__":
    main()
