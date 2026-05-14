"""Genera assets/app.ico (ejecutar una vez desde la raíz del proyecto)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "app.ico"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", (32, 32), (30, 144, 255, 255))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 4, 28, 28), radius=6, fill=(255, 255, 255, 230))
    d.rounded_rectangle((8, 10, 24, 24), radius=4, fill=(30, 144, 255, 255))
    im.save(OUT, format="ICO")
    print("Escrito:", OUT)


if __name__ == "__main__":
    main()
