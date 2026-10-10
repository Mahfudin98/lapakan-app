"""Membuat petatoko.ico (pin lokasi putih di atas kotak indigo). Jalankan: python make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
OUT = Path(__file__).with_name("petatoko.ico")


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=110, fill=(79, 70, 229, 255))  # indigo-600
    cx, cy, r = SIZE // 2, 205, 118
    # kepala pin + ujung runcing
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    d.polygon([(cx - 100, cy + 62), (cx + 100, cy + 62), (cx, 440)], fill=(255, 255, 255, 255))
    d.ellipse((cx - 52, cy - 52, cx + 52, cy + 52), fill=(79, 70, 229, 255))  # lubang pin
    return img


if __name__ == "__main__":
    draw().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ditulis:", OUT, OUT.stat().st_size, "byte")
