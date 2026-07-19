"""生成 PatWiki 应用图标。
用 Pillow 生成一个简洁的蓝色圆角方块 + "P" 字母图标。
输出: src-tauri/icons/icon.ico (多尺寸: 16,32,48,64,128,256)
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# 强制 stdout/stderr 用 utf-8，避免 Windows cp1252 无法编码中文/emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def make_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角背景（品牌蓝色 #1890ff）
    margin = int(size * 0.08)
    radius = int(size * 0.18)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=(24, 144, 255, 255),
    )

    # 中间画一个白色的 "P"（PatWiki 的 P）
    try:
        font = ImageFont.truetype("arial.ttf", int(size * 0.55))
    except OSError:
        font = ImageFont.load_default()

    text = "P"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2 - bbox[0]
    y = (size - text_h) // 2 - bbox[1]
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    return img


def main():
    out_dir = Path(__file__).parent.parent / "src-tauri" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    sizes = [16, 32, 48, 64, 128, 256]
    images = [make_icon(s) for s in sizes]

    # 保存 ICO（多尺寸打包在一个文件里）
    ico_path = out_dir / "icon.ico"
    images[-1].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"[OK] icon generated: {ico_path}")

    # 同时保存 PNG（某些 Tauri 版本需要）
    png_path = out_dir / "icon.png"
    images[-1].save(png_path, format="PNG")
    print(f"[OK] png generated: {png_path}")


if __name__ == "__main__":
    main()
