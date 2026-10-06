"""Render the vector logo. Requires resvg-py and Pillow."""
from pathlib import Path
from xml.etree import ElementTree

import resvg_py
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "brand"
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / "frontend" / "public" / "patwiki-logo.svg"

for size in (16, 32, 64, 128, 180, 192, 256, 512, 1024):
    (OUT / f"patwiki-icon-{size}.png").write_bytes(
        resvg_py.svg_to_bytes(svg_path=str(SOURCE), width=size, height=size)
    )
icon = Image.open(OUT / "patwiki-icon-1024.png")
icon.save(OUT / "patwiki.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
Image.open(OUT / "patwiki-icon-180.png").save(OUT / "apple-touch-icon.png")
svg = ElementTree.parse(SOURCE).getroot()
brand_color = svg.find("{http://www.w3.org/2000/svg}rect").attrib["fill"]
maskable = Image.new("RGBA", (512, 512), brand_color)
inset = icon.resize((384, 384), Image.Resampling.LANCZOS)
maskable.alpha_composite(inset, (64, 64))
maskable.save(OUT / "patwiki-maskable-512.png")
for name in ("patwiki-logo-mark", "patwiki-logo-wordmark", "patwiki-logo-preview"):
    source = OUT / f"{name}.svg" if name != "patwiki-logo-wordmark" else SOURCE.with_name(f"{name}.svg")
    (OUT / f"{name}.png").write_bytes(resvg_py.svg_to_bytes(svg_path=str(source), resources_dir=str(source.parent)))
print(f"Generated logo assets in {OUT}")
