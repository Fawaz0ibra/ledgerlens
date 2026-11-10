"""Draw each page's ground-truth boxes over its PNG, to check them by eye.

Run from the repo root, after drawing some pages:

    uv run ledgerlens-datagen --seed 7 --count 3 --out data/samples
    uv run python tools/box-overlay/overlay.py data/samples

The boxes come from the JSON files, not from the page, so the pictures show what the dataset says. They
go to boxes/ inside the folder. Orange: the Arabic copy of a value printed in both languages. Blue: the
English copy. Green: a value printed once.
"""

import base64
import sys
from pathlib import Path

from ledgerlens_datagen.layout import GroundTruth
from ledgerlens_datagen.render import PAGE_HEIGHT_PX, PAGE_WIDTH_PX, PNG_SCALE, open_renderer

COLOURS = {"ar": "#e8590c", "en": "#1c7ed6", None: "#2b8a3e"}


def overlay_html(truth: GroundTruth, png: bytes) -> str:
    # The page is the PNG at its CSS size, drawn at the PNG's scale, so one PNG pixel is still one pixel.
    boxes = []
    for box in truth.layout.fields:
        x0, y0, x1, y1 = (edge / PNG_SCALE for edge in box.png)
        boxes.append(
            f'<div style="left:{x0}px; top:{y0}px; width:{x1 - x0}px; height:{y1 - y0}px; '
            f'border-color:{COLOURS[box.lang]}"></div>'
        )
    image = base64.b64encode(png).decode("ascii")
    return (
        "<!doctype html><style>body { margin: 0; } "
        f"img {{ display: block; width: {PAGE_WIDTH_PX}px; height: {PAGE_HEIGHT_PX}px; }} "
        "div { position: absolute; box-sizing: border-box; border: 0.5px solid; }</style>"
        f'<img src="data:image/png;base64,{image}">' + "".join(boxes)
    )


def main() -> None:
    folder = Path(sys.argv[1])
    out = folder / "boxes"
    out.mkdir(exist_ok=True)
    pages = sorted(folder.glob("[0-9]*.json"))
    with open_renderer() as renderer:
        for path in pages:
            truth = GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))
            html = overlay_html(truth, path.with_suffix(".png").read_bytes())
            (out / path.with_suffix(".png").name).write_bytes(renderer.draw(html).png)
    print(f"drew the boxes of {len(pages)} pages into {out}")


if __name__ == "__main__":
    main()
