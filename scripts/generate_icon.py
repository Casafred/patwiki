"""Prepare desktop icons from the shared PatWiki brand asset (Pillow only)."""
from pathlib import Path

from PIL import Image


def make_icon(size: int = 256) -> Image.Image:
    root = Path(__file__).resolve().parents[1]
    source = root / "frontend" / "public" / "brand" / "patwiki-icon-1024.png"
    with Image.open(source) as image:
        return image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def main():
    out_dir = Path(__file__).resolve().parents[1] / "src-tauri" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    image = make_icon()
    image.save(out_dir / "icon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    image.save(out_dir / "icon.png", format="PNG")
    print(f"[OK] PatWiki desktop icons generated: {out_dir}")


if __name__ == "__main__":
    main()
