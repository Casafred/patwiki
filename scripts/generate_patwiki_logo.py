"""Render the vector logo. Requires resvg-py or CairoSVG, plus Pillow."""
from pathlib import Path
from xml.etree import ElementTree

try:
    import resvg_py
except ImportError:
    resvg_py = None
try:
    import cairosvg
except ImportError:
    cairosvg = None
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "brand"
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / "frontend" / "public" / "patwiki-logo.svg"
MONOCHROME_SOURCE = ROOT / "frontend" / "public" / "brand" / "patwiki-logo-monochrome.svg"


def render_svg(source: Path, width: int | None = None, height: int | None = None) -> bytes:
    if resvg_py is not None:
        return resvg_py.svg_to_bytes(svg_path=str(source), width=width, height=height)
    if cairosvg is not None:
        return cairosvg.svg2png(url=str(source), output_width=width, output_height=height)
    raise RuntimeError("Install resvg-py or CairoSVG to render PatWiki logo assets.")


for size in (16, 32, 64, 128, 180, 192, 256, 512, 1024):
    (OUT / f"patwiki-icon-{size}.png").write_bytes(
        render_svg(SOURCE, width=size, height=size)
    )
    (OUT / f"patwiki-monochrome-{size}.png").write_bytes(
        render_svg(MONOCHROME_SOURCE, width=size, height=size)
    )
icon = Image.open(OUT / "patwiki-icon-1024.png")
monochrome = Image.open(OUT / "patwiki-monochrome-1024.png")
monochrome.save(OUT / "patwiki.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
Image.open(OUT / "patwiki-icon-180.png").save(OUT / "apple-touch-icon.png")
svg = ElementTree.parse(SOURCE).getroot()
namespace = "{http://www.w3.org/2000/svg}"
brand_gradient = svg.find(f".//{namespace}linearGradient")
brand_color = brand_gradient.find(f"{namespace}stop").attrib["stop-color"] if brand_gradient is not None else "#075e63"
maskable = Image.new("RGBA", (512, 512), brand_color)
inset = icon.resize((384, 384), Image.Resampling.LANCZOS)
maskable.alpha_composite(inset, (64, 64))
maskable.save(OUT / "patwiki-maskable-512.png")
for name in ("patwiki-logo-mark", "patwiki-logo-wordmark", "patwiki-logo-preview", "patwiki-logo-correction-preview"):
    source = OUT / f"{name}.svg" if name != "patwiki-logo-wordmark" else SOURCE.with_name(f"{name}.svg")
    (OUT / f"{name}.png").write_bytes(render_svg(source))
print(f"Generated logo assets in {OUT}")
